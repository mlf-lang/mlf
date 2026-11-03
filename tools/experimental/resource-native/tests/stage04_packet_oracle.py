"""Independent Stage04 correspondence oracle. Never imports packet mapping code.

The sole project import is the PUBLIC fresh Stage03 metadata checker. Schema
names/declarations are frozen test data, not producer-derived expectations.
This module performs no native launch, compilation, graph or model evaluation.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat

NULL = 0xffffffff


def bounded_file(path, limit, declared_bytes=None, expected_sha256=None):
    """Read bounded regular storage, with pin and stable-identity checks.

    No read precedes the declared-size, path, lstat and open-fstat checks.
    Reading stops after at most limit+1 bytes even if the file grows.
    """
    if type(limit) is not int or not 0 <= limit <= 67108864:
        raise ValueError('invalid input ceiling')
    if declared_bytes is not None and (type(declared_bytes) is not int or not 0 <= declared_bytes <= limit):
        raise ValueError('invalid declared input size')
    if expected_sha256 is not None and (type(expected_sha256) is not str or re.fullmatch(r'[0-9a-f]{64}',expected_sha256) is None):
        raise ValueError('invalid declared input hash')
    if type(path) is not str:
        raise ValueError('input path must be a string')
    target=Path(path)
    if not target.is_absolute() or str(target)!=path or '..' in target.parts or any(p.is_symlink() for p in (target,*target.parents)):
        raise ValueError('unsafe evidence input path')
    identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    before=target.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= limit:
        raise ValueError('input is not a bounded regular file')
    if declared_bytes is not None and before.st_size!=declared_bytes:
        raise ValueError('declared input size differs from stat size')
    fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        opened=os.fstat(fd)
        if identity(opened)!=identity(before):raise ValueError('input changed before read')
        chunks=[];remaining=limit+1
        while remaining:
            chunk=os.read(fd,min(65536,remaining))
            if not chunk:break
            chunks.append(chunk);remaining-=len(chunk)
        payload=b''.join(chunks);after=os.fstat(fd)
        if identity(after)!=identity(before) or len(payload)!=before.st_size or len(payload)>limit:
            raise ValueError('input changed during bounded read')
        if any(p.is_symlink() for p in (target,*target.parents)) or identity(target.lstat())!=identity(after):
            raise ValueError('input replaced during bounded read')
        if expected_sha256 is not None and hashlib.sha256(payload).hexdigest()!=expected_sha256:
            raise ValueError('pinned input hash mismatch')
        return payload
    finally:
        os.close(fd)


TEST_DATA = Path(__file__).absolute().with_name('stage04_packet_cases.json')
TEST_CONFIG = json.loads(bounded_file(str(TEST_DATA),1048576,121155,'c79113b98f4fda03701953f65b9a47b073cc2d67eddd340b7b1fe206f03029ea'))
SCHEMA = TEST_CONFIG['schema_declarations']
TABLES = tuple(d['table'] for d in SCHEMA['domain_tables'])
ELEMENTS = {e['name']: e for e in SCHEMA['element_types']}


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def exact(actual, expected, path='correspondence'):
    """Type-exact comparison, including bool versus integer, with first path."""
    pending = [(actual, expected, path)]
    while pending:
        a, b, p = pending.pop()
        if type(a) is not type(b):
            raise AssertionError((p, 'type', type(a).__name__, type(b).__name__))
        if type(b) is dict:
            if set(a) != set(b):
                raise AssertionError((p, 'keys', sorted(a), sorted(b)))
            pending.extend((a[k], b[k], p + '.' + k) for k in reversed(tuple(b)))
        elif type(b) in (list, tuple):
            if len(a) != len(b):
                raise AssertionError((p, 'length', len(a), len(b)))
            pending.extend((a[i], b[i], p + '[' + str(i) + ']') for i in reversed(range(len(b))))
        elif a != b:
            raise AssertionError((p, 'value', a, b))


def string_pool(d):
    values = set()
    for table in ('schemes', 'uses'):
        values.update(r['name'] for r in d[table])
    for r in d['codes']:
        values.add(r['name']); values.add(canon(r['body_path']))
        values.update(c['name'] for c in r['captures'])
    for r in d['uses']:
        values.update(canon(p) for p in r['occurrences'])
    for r in d['shapes']:
        if r['source']['kind'] == 'legacy': values.add(r['source']['reference'])
    for r in d['sites']:
        values.add(canon(r['path']))
        if r['legacy_physical'] is not None: values.add(r['legacy_physical'])
    values.update(r['atom'] for r in d['types'] if r['tag'] == 'closed')
    values.update(r['name'] for r in d['nominal_fields'])
    for r in d['families']:
        values.add(r['name']); values.update(v['name'] for v in r['variants'])
    for r in d['introductions']:
        values.add(canon(r['generalize_path'])); values.add(canon(r['seal_path']))
    pool = bytearray(); offsets = {}
    for value in sorted(values):
        assert type(value) is str and '\x00' not in value
        offsets[value] = len(pool); pool.extend(value.encode('utf-8', 'strict')); pool.append(0)
    return list(pool), offsets


def instruction(raw, path):
    exact(set(path), {'root', 'name', 'segments'}, 'raw-path.keys')
    root = path['root']
    if root == 'entry':
        assert path['name'] is None
        node = raw['entry']
    else:
        assert root in ('function', 'thunk')
        node = raw['functions' if root == 'function' else 'codes'][path['name']]['body']
    for i, part in enumerate(path['segments']):
        if i % 2:
            assert part == 'body' and type(node) is dict
        else:
            assert type(part) is int and type(node) is list and 0 <= part < len(node)
        node = node[part]
    assert type(node) is dict
    return node


def supplement(raw, d):
    rows = []
    for site in d['sites']:
        family_id = variant_id = None
        op = instruction(raw, site['path'])
        if site['category'] == 'SUM':
            assert op['op'] in ('construct_nullary', 'construct_sum')
            family, = [f for f in d['families'] if f['name'] == op['family']]
            variant, = [v for v in family['variants'] if v['name'] == op['variant']]
            ty = d['types'][site['principal_type']]
            shape = d['shapes'][family['shape']]
            assert shape['kind'] == 'SUM'
            assert ty['tag'] == 'closed' and ty['atom'] == shape['source']['reference']
            if op['op'] == 'construct_nullary': assert not variant['fields']
            family_id, variant_id = family['id'], variant['index']
        else:
            assert op['op'] not in ('construct_nullary', 'construct_sum')
        rows.append({'site': site['id'], 'sum_family': family_id, 'sum_variant': variant_id})
    return {'format': 'resource-ir-v8-c-packet-site-supplement/1', 'sites': rows}


def source_inventory(d, pool):
    """Rebuild keys/counts independently, THEN compare Stage03's public inventory."""
    rows = []
    def add(kind, key, count, element):
        rows.append(dict(kind=kind, key=key, count=count, element_kind=element,
                         emission_status='planned-unbound'))
    for domain in SCHEMA['domain_tables']:
        t = domain['table']; n = len(d[t])
        add('table', 'table/' + t, n, 'meta.' + domain['element'])
        add('index', 'index/table/' + t, n, 'meta.RegisteredRowRef')
    descriptor_counts = (len(d['shapes']), len(d['codes']), len(d['families']),
                         sum(len(f['variants']) for f in d['families']),
                         len(d['nominal_fields']), sum(len(c['captures']) for c in d['codes']))
    for domain, n in zip(SCHEMA['domain_descriptors'], descriptor_counts):
        add('descriptor', 'descriptor/' + domain['suffix'], n, domain['source_element_kind'])
        add('index', 'index/descriptor/' + domain['suffix'], n, 'meta.RegisteredDescriptorRef')
    vectors = [('environments','env','arguments','ref.Type'),
               ('codes','code-captures','captures','meta.CaptureTyping'),
               ('code_executions','execution-captures','captures','meta.ResolvedCapture'),
               ('introductions','intro-sites','result_sites','ref.Site'),
               ('uses','use-occurrences','occurrences','ref.PathString')]
    for table, prefix, field, element in vectors:
        for r in d[table]: add('vector', 'vector/' + prefix + '/' + str(r['id']), len(r[field]), element)
    for f in d['families']:
        prefix = str(f['id'])
        add('vector','vector/family-variants/' + prefix,len(f['variants']),'meta.VariantTyping')
        add('vector','vector/family-variant-pointers/' + prefix,len(f['variants']),'physical.RtVariantRef')
        for v in f['variants']:
            add('vector','vector/variant-fields/' + prefix + '/' + str(v['index']),len(v['fields']),'ref.NominalField')
    for s in d['shapes']:
        if s['kind'] == 'DATA':
            add('vector','vector/data-fields/' + str(s['id']),sum(f['shape'] == s['id'] for f in d['nominal_fields']),'ref.NominalField')
    add('string-pool','pool/strings',len(pool),'byte.UTF8')
    add('header','header/bindings',5,'byte.Digest32')
    add('header','header/program',1,'physical.RtProgram')
    add('header','header/typed',1,'meta.TypedHeader')
    order = ('table','vector','descriptor','index','string-pool','header')
    rows.sort(key=lambda r:(order.index(r['kind']),r['key']))
    result = [dict(id=i, **row) for i,row in enumerate(rows)]
    exact(d['storage_inventory'], result, 'Stage03.storage_inventory')
    assert d['counts']['storage_entries'] == len(result)
    assert d['counts']['storage_objects'] == sum(r['count'] > 0 for r in result)
    return result


def object_identity(key):
    nulls = dict(owner=NULL, secondary_owner=NULL)
    for domain in SCHEMA['domain_tables']:
        for prefix,kind,element in [('table/',1,domain['element']),('index/table/',2,'RegisteredRowRef')]:
            if key == prefix + domain['table']: return dict(kind=kind,domain_or_subkind=domain['id'],element=element,**nulls)
    for domain in SCHEMA['domain_descriptors']:
        for prefix,kind,element in [('descriptor/',3,domain['element']),('index/descriptor/',4,'RegisteredDescriptorRef')]:
            if key == prefix + domain['suffix']: return dict(kind=kind,domain_or_subkind=domain['id'],element=element,**nulls)
    for v in SCHEMA['vector_subkinds']:
        prefix = v['key_prefix'] + '/'
        if key.startswith(prefix):
            ids = [int(x) for x in key[len(prefix):].split('/')]
            assert len(ids) == (2 if v['secondary_owner_domain'] else 1)
            return dict(kind=5,domain_or_subkind=v['id'],element=v['element'],owner=ids[0],secondary_owner=ids[1] if len(ids)==2 else NULL)
    for f in SCHEMA['fixed_objects']:
        if key == f['key']:
            return dict(kind=f['kind'],domain_or_subkind=f['domain_or_subkind'],element=f['element'],**nulls)
    raise AssertionError(('unknown inventory key',key))


def independent_expected(raw):
    from resource_ir_v8.metadata import check_metadata  # PUBLIC fresh check, never packet helpers.
    closure = check_metadata(raw)
    d = json.loads(closure.metadata_json)
    raw = json.loads(closure.canonical_json)
    assert d['native_status'] == dict(state='abi-unbound',typed_static_bytes=None,graph_executed=False,source_admitted=False)
    pool, strings = string_pool(d)
    inventory = source_inventory(d,pool)
    extra = supplement(raw,d)
    n = len(inventory)
    reordered = [inventory[i] for i in [n-2,n-1,n-3,*range(n-3)]]
    objects = []
    for r in reordered:
        objects.append(dict(key=r['key'],source_inventory_id=r['id'],count=r['count'],**object_identity(r['key'])))
    objects.append(dict(key='packet/object-directory',source_inventory_id=NULL,count=n+1,**object_identity('packet/object-directory')))
    by_key = {o['key']:i for i,o in enumerate(objects)}
    def span(key):
        i=by_key[key]; count=objects[i]['count']
        return dict(object=i if count else NULL,count=count)
    def val(x): return NULL if x is None else x
    def string(x): return NULL if x is None else strings[x if type(x) is str else canon(x)]
    def enum(domain,x): return NULL if x is None else SCHEMA['enums'][domain][x]
    def repr_for(ty,env):
        row, = [r for r in d['representation_resolutions'] if (r['type'],r['env'])==(ty,env)]
        return row['representation']
    def slice_(key,ids):
        if not ids: return (NULL,0,0)
        assert ids==list(range(ids[0],ids[0]+len(ids)))
        return by_key[key],ids[0],len(ids)
    values = {}
    def put(key,rows):
        assert len(rows)==objects[by_key[key]]['count'],key
        values[key]=rows
    # Flatten declarations directly from public field schemas; tagged nested
    # fields and shared vectors are explicitly mapped below, never introspected
    # from producer code or producer-specific private data.
    for domain in SCHEMA['domain_tables']:
        table=domain['table']; element=ELEMENTS[domain['element']]; rows=[]
        for r in d[table]:
            out={}
            for f in element['fields']:
                name,kind=f['name'],f['type']
                if name not in r: continue
                x=r[name]
                if kind in ('S','NS'): out[name]=string(x)
                elif kind.startswith(('U<','NU<')): out[name]=enum(kind.split('<')[1][:-1],x)
                elif kind.startswith('V<'): continue
                else: out[name]=val(x)
            i=str(r['id'])
            if table=='environments':out['arguments']=span('vector/env/'+i)
            elif table=='codes':out['captures']=span('vector/code-captures/'+i)
            elif table=='code_executions':out['captures']=span('vector/execution-captures/'+i)
            elif table=='shapes':
                src=r['source'];out.update(source_tag=enum('ShapeSource',src['kind']),source_reference=string(src.get('reference')),source_type=val(src.get('type')),source_scheme=val(src.get('scheme')))
            elif table=='families':out['variants']=span('vector/family-variants/'+i)
            elif table=='sites':
                ctx=r['context'];out.update(context_tag=enum('SiteContext',ctx['kind']),context_intro=val(ctx.get('intro')),context_code=val(ctx.get('code')),context_scheme=val(ctx.get('scheme')),
                                            sum_family=val(extra['sites'][r['id']]['sum_family']),sum_variant=val(extra['sites'][r['id']]['sum_variant']))
            elif table=='slots':
                role=r['role'];out.update(role_tag=enum('SlotRole',role['kind']),role_name=string(role.get('name')),role_variant=val(role.get('variant')),role_field=val(role.get('field')))
            elif table=='introductions':
                container=r['container'];out.update(container_tag=enum('IntroContainer',container['kind']),container_code=val(container.get('code')),result_sites=span('vector/intro-sites/'+i))
            elif table=='uses':out.update(arguments=span('vector/env/'+str(r['env'])),occurrences=span('vector/use-occurrences/'+i))
            assert set(out)=={f['name'] for f in element['fields']},(table,set(out))
            rows.append(out)
        put('table/'+table,rows)
        put('index/table/'+table,[dict(domain=domain['id'],row=i) for i in range(len(rows))])
    for r in d['environments']:put('vector/env/'+str(r['id']),[dict(row=t) for t in r['arguments']])
    for r in d['codes']:
        put('vector/code-captures/'+str(r['id']),[dict(name=string(c['name']),type=c['type'],relation=enum('Relation',c['relation'])) for c in r['captures']])
    for r in d['code_executions']:
        original=d['codes'][r['code']]['captures']
        assert [(c['name'],c['relation']) for c in r['captures']]==[(c['name'],c['relation']) for c in original]
        put('vector/execution-captures/'+str(r['id']),[dict(code=r['code'],position=i,type=c['type']) for i,c in enumerate(r['captures'])])
    for r in d['introductions']:put('vector/intro-sites/'+str(r['id']),[dict(row=s) for s in r['result_sites']])
    for r in d['uses']:put('vector/use-occurrences/'+str(r['id']),[dict(path=string(p)) for p in r['occurrences']])
    flattened = [(f,v) for f in d['families'] for v in f['variants']]
    variant_ids = {(f['id'],v['index']):i for i,(f,v) in enumerate(flattened)}
    for f in d['families']:
        key=str(f['id'])
        put('vector/family-variants/'+key,[dict(name=string(v['name']),index=v['index'],fields=span('vector/variant-fields/'+key+'/'+str(v['index']))) for v in f['variants']])
        put('vector/family-variant-pointers/'+key,[dict(row=variant_ids[f['id'],v['index']]) for v in f['variants']])
        for v in f['variants']:put('vector/variant-fields/'+key+'/'+str(v['index']),[dict(row=i) for i in v['fields']])
    for s in d['shapes']:
        if s['kind']=='DATA':put('vector/data-fields/'+str(s['id']),[dict(row=f['id']) for f in d['nominal_fields'] if f['shape']==s['id']])
    fields=[]
    for f in d['nominal_fields']:
        if f['variant'] is None:kind,owner=1,f['shape']
        else:
            family,=[x for x in d['families'] if x['shape']==f['shape']]
            kind,owner=2,variant_ids[family['id'],f['variant']]
        fields.append(dict(owner_kind=kind,owner=owner,position=f['position'],name=string(f['name']),type=f['type'],nominal_declared_rep=f['declared_rep'],code_principal_rep=NULL,relation=NULL))
    put('descriptor/nominal-fields',fields)
    shapes=[]
    for s in d['shapes']:
        ids=[f['id'] for f in d['nominal_fields'] if f['shape']==s['id']] if s['kind']=='DATA' else []
        obj,first,count=slice_('descriptor/nominal-fields',ids)
        typing,=[x for x in d['shape_typing'] if x['shape']==s['id']]
        rep,=[x for x in d['representations'] if x['shape']==s['id'] and x['typing']==typing['id']]
        shapes.append(dict(shape=s['id'],typing=typing['id'],representation=rep['id'],kind=enum('ShapeKind',s['kind']),fields_object=obj,field_first=first,field_count=count,argument_rep=val(s['argument_rep']),result_rep=val(s['result_rep'])))
    put('descriptor/shapes',shapes)
    variants=[]
    for f,v in flattened:
        obj,first,count=slice_('descriptor/nominal-fields',v['fields'])
        variants.append(dict(family=f['id'],index=v['index'],name=string(v['name']),shape=f['shape'],fields_object=obj,field_first=first,field_count=count))
    put('descriptor/variants',variants)
    put('descriptor/families',[dict(family=f['id'],shape=f['shape'],variants=span('vector/family-variant-pointers/'+str(f['id']))) for f in d['families']])
    captures=[];codes=[]
    for c in d['codes']:
        env=0 if c['scope'] is None else d['schemes'][c['scope']]['neutral_env']
        start=len(captures)
        for i,v in enumerate(c['captures']):
            captures.append(dict(owner_kind=3,owner=c['id'],position=i,name=string(v['name']),type=v['type'],nominal_declared_rep=NULL,code_principal_rep=repr_for(v['type'],env),relation=enum('Relation',v['relation'])))
        obj,first,count=slice_('descriptor/code-capture-fields',list(range(start,len(captures))))
        codes.append(dict(code=c['id'],principal_env=env,principal_rep=repr_for(c['callable_type'] if c['kind']=='function' else c['result'],env),capture_object=obj,capture_first=first,capture_count=count,body_binding=1))
    put('descriptor/code-capture-fields',captures);put('descriptor/codes',codes)
    for domain in SCHEMA['domain_descriptors']:
        key='descriptor/'+domain['suffix']
        put('index/'+key,[dict(domain=domain['id'],row=i) for i in range(len(values[key]))])
    bindings=[d['core_sha256'],closure.ir_sha256,closure.declaration_sha256,closure.resource_sha256,closure.metadata_sha256]
    put('header/bindings',[dict(bytes=list(bytes.fromhex(x))) for x in bindings]);put('pool/strings',pool)
    typed={}
    for field,domains,prefix in [('table',SCHEMA['domain_tables'],'table/'),('table_index',SCHEMA['domain_tables'],'index/table/'),('descriptor',SCHEMA['domain_descriptors'],'descriptor/'),('descriptor_index',SCHEMA['domain_descriptors'],'index/descriptor/')]:
        typed[field]=[span(prefix+x.get('table',x.get('suffix'))) for x in domains]
    put('header/typed',[typed])
    r_total=sum(len(d[t]) for t in ('type_resolutions','representation_resolutions','accesses','transports'))
    assert r_total==d['counts']['access_transport_resolution_rows']
    for o in objects:o['element_type']=ELEMENTS[o['element']]['element_type_id']
    mapping=[]
    for r in inventory:
        o=objects[by_key[r['key']]]
        klass='descriptor-specification' if r['kind']=='descriptor' else 'packet-header' if r['kind']=='header' else 'shared-reference' if r['key'].startswith('index/') or r['element_kind'].startswith('ref.') or r['element_kind']=='physical.RtVariantRef' else 'direct'
        mapping.append(dict(source_id=r['id'],key=r['key'],kind=r['kind'],count=r['count'],source_element_kind=r['element_kind'],packet_element_type=o['element'],directory_id=by_key[r['key']],mapping_class=klass))
    return dict(closure=closure,metadata=d,raw=raw,bindings=bindings,supplement=extra,
                objects=objects,values=values,source_inventory=inventory,mapping=mapping,R=r_total)


def verify_emission(raw, result):
    x=independent_expected(raw); c=x['closure']; d=x['metadata']
    exact(result.canonical_ir_json,c.canonical_json,'canonical raw')
    exact(result.metadata_json,c.metadata_json,'unchanged metadata')
    exact(result.bindings,tuple(x['bindings']),'bindings')
    exact(result.supplement_json,canon(x['supplement']),'supplement')
    exact(result.supplement_sha256,sha(result.supplement_json),'supplement hash')
    manifest=json.loads(result.manifest_json)
    exact(result.manifest_json,canon(manifest),'canonical manifest')
    exact(result.manifest_sha256,sha(result.manifest_json),'manifest hash')
    expected=dict(format='resource-ir-v8-c-packet-emission-manifest/1',schema_sha256=TEST_CONFIG['schema_sha256'],
                  bindings=dict(zip(('core','raw','declaration','resource','metadata'),x['bindings'])),supplement_sha256=sha(canon(x['supplement'])),
                  table_counts={t:len(d[t]) for t in TABLES},resolution_access_transport_rows=x['R'],source_inventory_entries=x['mapping'],
                  packet_directory_count=len(x['objects']),packet_member_count=sum(o['count']>0 for o in x['objects']),
                  host_sidecars=dict(metadata_sha256=c.metadata_sha256,resource_sha256=c.resource_sha256,supplement_sha256=sha(canon(x['supplement']))),
                  outputs={name:dict(bytes=len(getattr(result,name).encode()),sha256=sha(getattr(result,name))) for name in ('packet_header','packet_source')},
                  native_status=dict(state='uncompiled-packet-only',packet_bytes=None,runtime_total_static_bytes=None,graph_executed=False,source_admitted=False,runtime_guards_executed=False))
    exact(manifest,expected,'emission manifest')
    verify_source_text(x,result.packet_header,result.packet_source)
    return x


def verify_report(report, status, support=None):
    """Validate every report field, including the success diagnostic sentinel."""
    fields=next(t['fields'] for t in SCHEMA['non_element_types'] if t['name']=='Report')
    assert type(report) is dict
    exact(set(report),{f['name'] for f in fields},'report keys')
    for field in fields:
        value=report[field['name']]
        maximum=SCHEMA['limits']['native_work'] if field['name']=='work_used' else NULL
        assert type(value) is int and 0<=value<=maximum,('report integer',field['name'])
    assert type(status) is int and status in SCHEMA['enums']['NativeStatus'].values()
    exact(report['status'],status,'outer status equals report status')
    assert report['phase']==NULL or report['phase'] in SCHEMA['enums']['NativePhase'].values()
    assert report['detail'] in SCHEMA['enums']['NativeDetail'].values()
    for flag in ('graph_executed','source_admitted','runtime_admitted','runtime_guards_executed'):
        exact(report[flag],0,flag)
    assert 0<report['workspace_bytes']<=SCHEMA['limits']['native_workspace_bytes']
    assert report['workspace_bytes']<=report['work_used']
    if support is not None:exact(report['workspace_bytes'],support['workspace_bytes'],'actual workspace sizeof')
    assert report['packet_bytes']<=SCHEMA['limits']['packet_bytes']
    assert report['member_bytes_sum']<=report['packet_bytes'] and report['padding_bytes']<=report['packet_bytes']
    assert report['directory_entries']<=SCHEMA['limits']['directory_entries']
    assert report['member_objects']<=report['directory_entries']
    assert report['resolution_access_transport_rows']<=SCHEMA['limits']['R']
    if status==0:
        exact(report['phase'],SCHEMA['enums']['NativePhase']['final-census'],'success phase')
        exact(report['detail'],SCHEMA['enums']['NativeDetail']['none'],'success detail')
        for field in ('domain','object','row','field'):exact(report[field],NULL,'success '+field)
    return report


def verify_support(support, baseline):
    """Actual harness allocations remain separate from production packet storage.

    C padding is implementation-defined. Report/workspace sizeof must cover all
    declared payload fields and obey their reviewed bounds, not a guessed ABI.
    """
    names={'workspace_bytes','report_bytes','copy_allocation_bytes','mutation_snapshot_bytes','expected_bindings_bytes'}
    assert type(support) is dict;exact(set(support),names,'support keys')
    for name,value in support.items():assert type(value) is int and value>0,('support integer',name)
    root_bytes=baseline['root_bytes']
    assert type(root_bytes) is int and 0<root_bytes<=SCHEMA['limits']['packet_bytes']
    definitions={t['name']:t for t in SCHEMA['non_element_types']}
    definitions.update({t['name']:t for t in SCHEMA['element_types']})
    def payload_floor(kind):
        array=re.fullmatch(r'([^\[]+)((?:\[[0-9]+\])+)',kind)
        if array:
            size=payload_floor(array[1])
            for count in re.findall(r'\[([0-9]+)\]',array[2]):size*=int(count)
            return size
        if kind=='unsigned-char':return 1
        if kind=='uint64_t':return 8
        if kind=='uint32_t' or kind=='Flag' or kind in ('U','NU') or kind.startswith(('U<','NU<')):return 4
        return sum(payload_floor(f['type']) for f in definitions[kind]['fields'])
    assert payload_floor('Workspace')<=support['workspace_bytes']<=SCHEMA['limits']['native_workspace_bytes']
    assert payload_floor('Report')<=support['report_bytes']<=SCHEMA['limits']['native_function_stack_bytes']
    digest_id=ELEMENTS['Digest32']['element_type_id']
    digest_sizes=[entry['bytes'] for entry in baseline['abi'] if entry['element_type']==digest_id]
    assert len(digest_sizes)==1 and type(digest_sizes[0]) is int and digest_sizes[0]>=payload_floor('Digest32')
    # A private harness support ceiling, not a guessed struct layout.
    assert 5*digest_sizes[0]<=support['expected_bindings_bytes']<=4096
    exact(support['copy_allocation_bytes'],root_bytes+1,'copy allocation includes byte offset')
    exact(support['mutation_snapshot_bytes'],root_bytes,'mutation snapshot extent')
    exact(baseline['report']['workspace_bytes'],support['workspace_bytes'],'baseline workspace sizeof')
    return support


def verify_native(raw, native, support=None):
    """Native values are actual scalar readback, never emitted expectations.

    Layout references below come from literal C offsetof/sizeof in the separate
    harness, not copied directory fields; every directory value is compared to
    those measurements and the independently reconstructed inventory.
    """
    x=independent_expected(raw)
    assert type(native) is dict
    exact(set(native),{'format','status','report','root_bytes','root_alignment','abi','census','directory','objects'},'readback keys')
    exact(native['format'],'ir8-stage04-native-readback/1')
    exact(native['status'],0,'baseline validator status')
    report=verify_report(native['report'],native['status'],support)
    assert type(native['root_bytes']) is int and 0<native['root_bytes']<=4194304
    assert type(native['root_alignment']) is int and 0<native['root_alignment']<=NULL
    assert native['root_bytes']%native['root_alignment']==0
    exact(report['packet_bytes'],native['root_bytes'],'report size')
    exact(report['declared_packet_alignment'],native['root_alignment'],'report alignment')
    exact(report['resolution_access_transport_rows'],x['R'],'report R')
    abi=native['abi'];exact([a['element_type'] for a in abi],list(range(1,41)),'ABI element IDs')
    abi_by={a['element_type']:a for a in abi}
    for declaration, measured in zip(SCHEMA['element_types'],abi):
        assert type(measured) is dict
        exact(set(measured),{'element_type','bytes','alignment','field_offsets','field_bytes'},'ABI measurement keys')
        for key in ('element_type','bytes','alignment'):assert type(measured[key]) is int and 0<measured[key]<=NULL
        names=[] if declaration['kind']=='scalar' else [f['name'] for f in declaration['fields']]
        exact(list(measured['field_offsets']),names,'measured field declaration order')
        exact(list(measured['field_bytes']),names,'measured field extent order')
        previous=0
        for name in names:
            off=measured['field_offsets'][name];size=measured['field_bytes'][name]
            assert type(off) is int and type(size) is int and off>=previous and size>0
            assert off+size<=measured['bytes'];previous=off+size
        assert measured['bytes']>0 and measured['alignment']>0 and measured['bytes']%measured['alignment']==0
    exact(len(native['census']),len(x['objects']),'full census count')
    exact(len(native['directory']),len(x['objects']),'full directory count')
    members=0;last=0;member_sum=0
    for i,(o,census,directory) in enumerate(zip(x['objects'],native['census'],native['directory'])):
        layout=abi_by[o['element_type']]
        assert type(census) is dict
        exact(set(census),{'object','count','offset','element_bytes','element_alignment','object_bytes'},'member census keys')
        for value in census.values():assert type(value) is int and 0<=value<=NULL
        assert native['root_alignment']%layout['alignment']==0
        exact(census['object'],i,'census id');exact(census['count'],o['count'],'census count')
        exact(census['element_bytes'],layout['bytes'],'element sizeof')
        exact(census['element_alignment'],layout['alignment'],'element alignment')
        exact(census['object_bytes'],o['count']*layout['bytes'],'member sizeof')
        offset=census['offset']
        if o['count']:
            assert type(offset) is int and offset>=last and offset%layout['alignment']==0
            assert offset<=native['root_bytes'] and census['object_bytes']<=native['root_bytes']-offset
            last=offset+census['object_bytes'];members+=1;member_sum+=census['object_bytes']
        else:exact(offset,NULL,'empty offset')
        expected={k:o[k] for k in ('source_inventory_id','kind','domain_or_subkind','owner','secondary_owner','element_type','count')}
        expected.update({k:census[k] for k in ('offset','element_bytes','element_alignment','object_bytes')})
        exact(directory,expected,'directory['+str(i)+']')
    exact(report['member_objects'],members,'member count');exact(report['member_bytes_sum'],member_sum,'member sum')
    exact(report['padding_bytes'],native['root_bytes']-member_sum,'root padding')
    exact(report['directory_entries'],len(x['objects']),'directory count')
    expected_values=dict(x['values'])
    keys={o['key']:i for i,o in enumerate(x['objects'])}
    expected_values['header/program']=[dict(magic=list(b'IR8PKT01'),abi_revision=1,purpose=1,packet_bytes=native['root_bytes'],packet_alignment=native['root_alignment'],directory_offset=native['census'][-1]['offset'],directory_count=len(x['objects']),typed_header_object=keys['header/typed'],bindings_object=keys['header/bindings'],string_pool_object=keys['pool/strings'] if x['objects'][keys['pool/strings']]['count'] else NULL,resolution_access_transport_rows=x['R'])]
    expected_values['packet/object-directory']=native['directory']
    exact([v['object'] for v in native['objects']],list(range(len(x['objects']))),'complete object IDs')
    for o,actual in zip(x['objects'],native['objects']):
        assert type(actual) is dict;exact(set(actual),{'object','rows'},'readback object keys')
        exact(actual['rows'],expected_values[o['key']],o['key'])
    return dict(status='independent-correspondence-passed',metadata_sha256=x['closure'].metadata_sha256,supplement_sha256=sha(canon(x['supplement'])),packet_bytes=native['root_bytes'],padding_bytes=report['padding_bytes'],runtime_total_static_bytes=None,graph_executed=False,source_admitted=False)


def verify_specification(raw, candidate):
    """Candidate is observed implementation output, NEVER expected authority."""
    x=independent_expected(raw)
    expected=[]
    source={r['key']:r for r in x['source_inventory']}
    for i,o in enumerate(x['objects']):
        r=source.get(o['key'])
        mapping=x['mapping'][r['id']]['mapping_class'] if r else 'direct'
        rows=[] if o['element'] in ('ProgramHeader','TypedHeader','ObjectDirectoryEntry') else x['values'][o['key']]
        expected.append(dict(source_id=r['id'] if r else None,key=o['key'],source_kind=r['kind'] if r else None,source_element_kind=r['element_kind'] if r else None,
                             kind=o['kind'],domain=o['domain_or_subkind'],owner=None if o['owner']==NULL else o['owner'],secondary_owner=None if o['secondary_owner']==NULL else o['secondary_owner'],
                             element=o['element'],count=o['count'],rows=rows,mapping_class=mapping,directory_id=i))
    actual=dict(format='resource-ir-v8-c-packet-specification/1',bindings=x['bindings'],supplement=x['supplement'],objects=expected,resolution_access_transport_rows=x['R'])
    exact(candidate,actual,'independent specification')
    return x


def verify_source_text(x, header, source):
    """Parse the complete fixed C initializer grammar without C execution.

    All 31 public emissions are compared field by field. Compiler expressions
    remain exact expressions here; they become measurements only natively.
    """
    import re
    root='struct Ir8Packet_generated_v1'
    ctype=lambda o:ELEMENTS[o['element']]['c_type']
    offset=lambda i:'offsetof('+root+',o'+str(i)+')'
    extent=lambda i:'sizeof((('+root+' *)0)->o'+str(i)+')'
    expected_header='#ifndef IR8_PACKET_GENERATED_H\n#define IR8_PACKET_GENERATED_H\n#include "ir8_packet.h"\n'+root+' {\n'
    for i,o in enumerate(x['objects']):
        if o['count']:expected_header+='    '+ctype(o)+' o'+str(i)+'['+str(o['count'])+'];\n'
    expected_header+='};\nconst void *ir8_packet_generated_data(void);\nsize_t ir8_packet_generated_size(void);\n#endif\n'
    exact(header,expected_header,'complete generated header')
    prefix='#include "ir8_packet_generated.h"\n'
    prefix+='_Static_assert(sizeof('+root+') <= UINT32_C(4194304), "packet byte limit");\n'
    prefix+='_Static_assert(_Alignof('+root+') <= UINT32_MAX, "packet alignment width");\n'
    prefix+='_Static_assert(offsetof('+root+',o0) == 0, "program header first");\n'
    for i,o in enumerate(x['objects']):
        prefix+='_Static_assert(sizeof('+ctype(o)+') <= UINT32_MAX && _Alignof('+ctype(o)+') <= UINT32_MAX, "element measurement width");\n'
        if o['count']:prefix+='_Static_assert('+offset(i)+' <= UINT32_MAX && '+extent(i)+' <= UINT32_MAX, "member measurement width");\n'
    prefix+='static const '+root+' ir8_packet_generated_root = '
    suffix=';\nconst void *ir8_packet_generated_data(void) { return &ir8_packet_generated_root; }\nsize_t ir8_packet_generated_size(void) { return sizeof(ir8_packet_generated_root); }\n'
    assert source.startswith(prefix) and source.endswith(suffix),'complete production source envelope'
    text=source[len(prefix):-len(suffix)];position=0
    def skip():
        nonlocal position
        while position<len(text) and text[position] in ' \n':position+=1
    def token(literal):
        nonlocal position
        skip();assert text.startswith(literal,position),(position,literal)
        position+=len(literal)
    def parse(depth=0):
        nonlocal position
        assert depth<16;skip()
        if text.startswith('{',position):
            position+=1;skip();named=text.startswith('.',position);result={} if named else []
            if text.startswith('}',position):position+=1;return result
            while True:
                if named:
                    token('.');match=re.match(r'[A-Za-z_][A-Za-z0-9_]*',text[position:]);assert match
                    key=match.group();position+=len(key);token('=');assert key not in result
                    result[key]=parse(depth+1)
                else:result.append(parse(depth+1))
                skip()
                if text.startswith('}',position):position+=1;return result
                token(',')
        if text.startswith('UINT32_C(',position):
            position+=9;match=re.match(r'(?:0|[1-9][0-9]*)\)',text[position:]);assert match
            number=int(match.group()[:-1]);assert 0<=number<=NULL;position+=len(match.group());return number
        for operator in ('sizeof','_Alignof','offsetof'):
            if text.startswith(operator+'(',position):
                start=position;position+=len(operator);level=0
                while position<len(text):
                    char=text[position];assert char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_ (),*->'
                    if char=='(':level+=1
                    elif char==')':
                        level-=1
                        if level==0:position+=1;return text[start:position]
                    position+=1
                raise AssertionError('unterminated compiler expression')
        match=re.match(r'(?:0|[1-9][0-9]*)',text[position:]);assert match,(position,text[position:position+40])
        position+=len(match.group());number=int(match.group());assert 0<=number<=255
        return number
    actual=parse();skip();assert position==len(text),'trailing initializer text'
    values=dict(x['values']);keys={o['key']:i for i,o in enumerate(x['objects'])}
    values['header/program']=[dict(magic=list(b'IR8PKT01'),abi_revision=1,purpose=1,packet_bytes='sizeof('+root+')',packet_alignment='_Alignof('+root+')',directory_offset=offset(len(x['objects'])-1),directory_count=len(x['objects']),typed_header_object=keys['header/typed'],bindings_object=keys['header/bindings'],string_pool_object=keys['pool/strings'] if x['objects'][keys['pool/strings']]['count'] else NULL,resolution_access_transport_rows=x['R'])]
    directory=[]
    for i,o in enumerate(x['objects']):
        row={k:o[k] for k in ('source_inventory_id','kind','domain_or_subkind','owner','secondary_owner','element_type','count')}
        row.update(offset=offset(i) if o['count'] else NULL,element_bytes='sizeof('+ctype(o)+')',element_alignment='_Alignof('+ctype(o)+')',object_bytes=extent(i) if o['count'] else 0)
        directory.append(row)
    values['packet/object-directory']=directory
    def positional(v):
        if type(v) is dict:
            if set(v)=={'object','count'}:return [v['object'],v['count']]
            return {k:positional(w) for k,w in v.items()}
        if type(v) is list:return [positional(w) for w in v]
        return v
    expected={'o'+str(i):positional(values[o['key']]) for i,o in enumerate(x['objects']) if o['count']}
    exact(list(actual),list(expected),'complete aggregate member order')
    exact(actual,expected,'parsed production initializer')
