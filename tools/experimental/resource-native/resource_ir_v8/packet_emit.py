"""Fresh metadata to one immutable C aggregate, without processes or target code.

All source syntax is fixed vocabulary plus checked decimal integers. User strings
occur only in the sole byte pool. This module never invokes a compiler/runtime.
"""
from __future__ import annotations

from .packet_budget import Budget, Writer, encode, exact, fail, same, uint
from .packet_schema import (TABLES, DESCRIPTORS, ELEMENTS, VECTORS, ENUMS, LIMITS,
                            NULL, ROOT_TYPE, ROOT_SYMBOL, HEADER_NAME)

_ELEMENT = {name: (ctype, number, fields) for name, ctype, number, fields in ELEMENTS}
_TAGS = {name: dict(values) for name, values in ENUMS.items()}
_DOMAIN = {element: table for table, element, domain in TABLES}
_ROW_KEYS = {
    'types': ('id','tag','atom','scheme','index','argument','result','protocol','result_identity'),
    'callable_contracts': ('id','type','argument','result','protocol','result_identity'),
    'schemes': ('id','name','parameters','body','neutral_env','intro'),
    'environments': ('id','scheme','mode','arguments'),
    'codes': ('id','kind','name','scope','callable_type','argument','result','captures','body_path','expected_protocol','expected_identity_flag'),
    'code_executions': ('id','code','env','callable_type','argument','result','captures'),
    'shapes': ('id','source','kind','argument_rep','result_rep'),
    'shape_typing': ('id','shape','type','scope','contract'),
    'representations': ('id','shape','typing','ready_kind'),
    'nominal_fields': ('id','shape','variant','position','name','type','declared_rep'),
    'families': ('id','name','shape','variants'),
    'type_resolutions': ('id','type','env','result'),
    'representation_resolutions': ('id','type','env','representation'),
    'sites': ('id','path','arm','scope','principal_type','category','code','legacy_physical','context'),
    'site_executions': ('id','site','env','origin_kind','principal_type','representation','code_execution'),
    'slots': ('id','site','role','type','relation'),
    'accesses': ('id','site','origin_env','mode','use_env','type','scheme'),
    'introductions': ('id','scheme','container','generalize_path','seal_path','body_type','result_sites'),
    'uses': ('id','name','scheme','arguments','env','result_type','occurrences'),
    'transports': ('id','source_access','projection_env','result_access','kind'),
}
_SOURCE_ELEMENTS = ('meta.Type','meta.CallableContract','meta.Scheme','meta.Env','meta.CodeTyping',
    'meta.CodeExecution','meta.ShapeBinding','meta.ShapeTyping','meta.Representation',
    'meta.NominalField','meta.FamilyTyping','meta.TypeResolution','meta.RepresentationResolution',
    'meta.Site','meta.SiteExecution','meta.Slot','meta.Access','meta.Intro','meta.Use','meta.Transport')
_VECTOR_SOURCE = ('ref.Type','meta.CaptureTyping','meta.ResolvedCapture','ref.Site','ref.PathString',
                  'meta.VariantTyping','physical.RtVariantRef','ref.NominalField','ref.NominalField')


def _error(path, code, message):
    fail(path, 'packet-mapping', code, message)


def _name(value, path, budget):
    if type(value) is not str:
        fail(path, 'packet-schema', 'SCHEMA', 'expected a plain string')
    for char in value:
        budget.work()
        if ord(char) == 0 or 0xD800 <= ord(char) <= 0xDFFF:
            fail(path, 'packet-schema', 'SCHEMA', 'string is not non-NUL Unicode scalar text')
    return value


def _path_text(value, budget):
    exact(value, ('root','name','segments'), 'packet.path', budget)
    if value['root'] not in ('entry','function','thunk') or type(value['segments']) is not list:
        fail('packet.path', 'packet-schema', 'SCHEMA', 'invalid checked path')
    if (value['root'] == 'entry') != (value['name'] is None):
        fail('packet.path', 'packet-schema', 'NULL_DOMAIN', 'invalid path name domain')
    if value['name'] is not None:
        _name(value['name'], 'packet.path.name', budget)
    for segment in value['segments']:
        budget.work()
        if type(segment) is int:
            uint(segment, 'packet.path.segments')
        elif segment != 'body' or type(segment) is not str:
            fail('packet.path.segments', 'packet-schema', 'SCHEMA', 'invalid path segment')
    # Canonical path JSON is shared as one scalar string in the unique pool.
    return encode(value, budget, 'path', LIMITS['production_source_bytes'])[0]


def _instruction(raw, path, budget):
    _path_text(path, budget)
    if path['root'] == 'entry':
        current = raw['entry']
    else:
        bank = raw['functions' if path['root'] == 'function' else 'codes']
        if path['name'] not in bank:
            _error('packet.supplement', 'SUPPLEMENT', 'callback path is absent')
        current = bank[path['name']]['body']
    for segment in path['segments']:
        budget.work()
        if type(segment) is int and type(current) is list and segment < len(current):
            current = current[segment]
        elif segment == 'body' and type(current) is dict and current.get('op') == 'generalize':
            current = current['body']
        else:
            _error('packet.supplement', 'SUPPLEMENT', 'Site path does not identify raw syntax')
    if type(current) is not dict or type(current.get('op')) is not str:
        _error('packet.supplement', 'SUPPLEMENT', 'Site path is not an instruction')
    return current


def _supplement(raw, metadata, budget):
    budget.creation(3)
    names, sites = {}, []
    for family in metadata['families']:
        budget.work()
        if family['name'] in names:
            _error('packet.supplement', 'SUPPLEMENT', 'duplicate family name')
        budget.put(names, family['name'], family)
    for site in metadata['sites']:
        budget.reserve(creation=12, work=1)
        instruction = _instruction(raw, site['path'], budget)
        family_id = variant_id = None
        constructor = instruction['op'] in ('construct_nullary','construct_sum')
        if site['category'] == 'SUM':
            if not constructor or instruction['family'] not in names:
                _error('packet.supplement', 'SUPPLEMENT', 'SUM site is not its literal constructor')
            family = names[instruction['family']]
            declared = raw['families'][instruction['family']]
            for index, name in enumerate(declared['variants']):
                budget.work()
                if name == instruction['variant']:
                    if variant_id is not None:
                        _error('packet.supplement', 'SUPPLEMENT', 'ambiguous declared variant')
                    variant_id = index
            if variant_id is None or variant_id >= len(family['variants']):
                _error('packet.supplement', 'SUPPLEMENT', 'literal variant is absent')
            variant = family['variants'][variant_id]
            if variant['index'] != variant_id or variant['name'] != instruction['variant']:
                _error('packet.supplement', 'SUPPLEMENT', 'declared family order differs')
            shape = metadata['shapes'][family['shape']]
            typing = metadata['shape_typing'][family['shape']]
            principal = metadata['types'][site['principal_type']]
            if (shape['kind'] != 'SUM' or typing['shape'] != family['shape']
                    or typing['type'] != site['principal_type'] or principal['tag'] != 'closed'
                    or principal['atom'] != '%' + family['name']):
                _error('packet.supplement', 'SUPPLEMENT', 'selected family has a different nominal principal type')
            for execution in metadata['site_executions']:
                budget.work()
                if execution['site'] == site['id']:
                    representation = metadata['representations'][execution['representation']]
                    if representation['shape'] != family['shape']:
                        _error('packet.supplement', 'SUPPLEMENT', 'selected family has a different site representation')
            if instruction['op'] == 'construct_nullary' and (declared['fields'][instruction['variant']] or variant['fields']):
                _error('packet.supplement', 'SUPPLEMENT', 'nullary constructor has fields')
            family_id = family['id']
        elif constructor:
            _error('packet.supplement', 'SUPPLEMENT', 'constructor Site is not SUM')
        budget.append(sites, budget.row(site=site['id'], sum_family=family_id, sum_variant=variant_id))
    budget.creation(3)
    return budget.row(format='resource-ir-v8-c-packet-site-supplement/1', sites=sites)


class Projection:
    """Invocation-owned bounded maps; never retained by PacketEmission."""
    __slots__ = ('raw','metadata','bindings','budget','objects','by_key','strings','pool',
                 'supplement','variant_ids','resolutions','source_inventory')

    def __new__(cls, raw, metadata, bindings, budget):
        # Instance header, twelve retained slots, and seven owned container headers.
        # Reserve before allocating the instance or assigning any retained field.
        budget.creation(20)
        return object.__new__(cls)

    def __init__(self, raw, metadata, bindings, budget):
        self.raw, self.metadata, self.bindings, self.budget = raw, metadata, bindings, budget
        self.objects, self.by_key, self.strings, self.pool = [], {}, {}, []
        self.variant_ids, self.resolutions, self.source_inventory = {}, {}, []
        self.supplement = _supplement(raw, metadata, budget)
        for table, _, _ in TABLES:
            if type(metadata[table]) is not list:
                fail('packet.tables.' + table, 'packet-schema', 'SCHEMA', 'expected a table array')
            for index, row in enumerate(metadata[table]):
                budget.reserve(creation=4, work=1)
                exact(row, _ROW_KEYS[table], 'packet.tables.' + table, budget)
                if uint(row['id'], 'packet.tables.' + table + '.id') != index:
                    _error('packet.tables.' + table, 'REFERENCE', 'row IDs are not contiguous')
        for row in metadata['representation_resolutions']:
            budget.work()
            key = budget.pair(row['type'], row['env'])
            if key in self.resolutions:
                _error('packet.representations', 'EQUATION', 'duplicate resolution key')
            budget.put(self.resolutions, key, row['representation'])
        flat = 0
        for family in metadata['families']:
            for variant in family['variants']:
                budget.work()
                budget.put(self.variant_ids, budget.pair(family['id'],variant['index']), flat)
                flat += 1
        self.make_pool()
        self.inventory()

    def make_pool(self):
        b, m = self.budget, self.metadata
        b.creation()
        texts = set()
        def add(text):
            _name(text, 'packet.strings', b)
            b.work()
            if text not in texts:
                b.creation()
                texts.add(text)
        def path(value):
            add(_path_text(value, b))
        for row in m['schemes']: add(row['name'])
        for row in m['codes']:
            add(row['name']); path(row['body_path'])
            for capture in row['captures']: add(capture['name'])
        for row in m['uses']:
            add(row['name'])
            for occurrence in row['occurrences']: path(occurrence)
        for row in m['shapes']:
            if row['source']['kind'] == 'legacy': add(row['source']['reference'])
        for row in m['sites']:
            path(row['path'])
            if row['legacy_physical'] is not None: add(row['legacy_physical'])
        for row in m['types']:
            if row['tag'] == 'closed': add(row['atom'])
        for row in m['nominal_fields']: add(row['name'])
        for row in m['families']:
            add(row['name'])
            for variant in row['variants']: add(variant['name'])
        for row in m['introductions']:
            path(row['generalize_path']); path(row['seal_path'])
        for text in b.ordered(texts):
            b.work()
            b.put(self.strings, text, len(self.pool))
            # Reserve all UTF-8 bytes as vector memberships before encoding.
            size = 1
            for char in text:
                b.work(); n = ord(char)
                size += 1 if n < 128 else 2 if n < 2048 else 3 if n < 65536 else 4
            if size > LIMITS['production_source_bytes'] - len(self.pool):
                fail('packet.pool', 'packet-bounds', 'SOURCE_BYTES', 'string pool exceeds source byte ceiling')
            b.reserve(creation=1 + size, work=size)
            self.pool.extend(text.encode('utf-8'))
            self.pool.append(0)

    def add_inventory(self, kind, key, count, source_element, element, domain, owner=None, secondary=None, mapping='direct'):
        b = self.budget
        b.reserve(creation=30, work=1)
        uint(count, 'packet.inventory.count')
        if len(self.source_inventory) + 2 > LIMITS['directory_entries']:
            fail('packet.directory', 'packet-bounds', 'DIRECTORY_COUNT', 'packet directory quota exhausted')
        entry = b.row(kind=kind, key=key, count=count, element_kind=source_element, emission_status='planned-unbound')
        b.append(self.source_inventory, entry)
        obj = b.row(source_id=None,key=key,source_kind=kind,source_element_kind=source_element,
                    kind={'table':1,'vector':5,'descriptor':3,'string-pool':6,'header':7,
                          'index':2 if key.startswith('index/table/') else 4}[kind],
                    domain=domain,owner=owner,secondary_owner=secondary,element=element,
                    count=count,rows=b.listing(),mapping_class=mapping)
        b.put(self.by_key, key, obj)

    def inventory(self):
        m, b = self.metadata, self.budget
        for index, (table, element, domain) in enumerate(TABLES):
            b.reserve(creation=2,work=2)  # table and table-index key concatenations
            self.add_inventory('table','table/'+table,len(m[table]),_SOURCE_ELEMENTS[index],element,domain)
            self.add_inventory('index','index/table/'+table,len(m[table]),'meta.RegisteredRowRef','RegisteredRowRef',domain,mapping='shared-reference')
        variants = len(self.variant_ids)
        captures = 0
        for code in m['codes']:
            b.work(); captures += len(code['captures'])
        b.creation(7)
        counts = (len(m['shapes']),len(m['codes']),len(m['families']),variants,len(m['nominal_fields']),captures)
        for (suffix,element,domain,source), count in zip(DESCRIPTORS,counts):
            b.reserve(creation=2,work=2)  # descriptor and descriptor-index keys
            self.add_inventory('descriptor','descriptor/'+suffix,count,source,element,domain,mapping='descriptor-specification')
            self.add_inventory('index','index/descriptor/'+suffix,count,'meta.RegisteredDescriptorRef','RegisteredDescriptorRef',domain,mapping='shared-reference')
        def vector(number, owner, count, secondary=None):
            prefix, element, domain, _, _ = VECTORS[number-1]
            b.creation(3)
            key = prefix + '/' + str(owner)
            if secondary is not None:
                b.creation(3); key += '/' + str(secondary)
            self.add_inventory('vector',key,count,_VECTOR_SOURCE[number-1],element,domain,owner,secondary,
                               'shared-reference' if number in (1,4,5,7,8,9) else 'direct')
        for env in m['environments']: vector(1,env['id'],len(env['arguments']))
        for code in m['codes']: vector(2,code['id'],len(code['captures']))
        for execution in m['code_executions']: vector(3,execution['id'],len(execution['captures']))
        for intro in m['introductions']: vector(4,intro['id'],len(intro['result_sites']))
        for use in m['uses']: vector(5,use['id'],len(use['occurrences']))
        for family in m['families']:
            vector(6,family['id'],len(family['variants']))
            vector(7,family['id'],len(family['variants']))
            for variant in family['variants']: vector(8,family['id'],len(variant['fields']),variant['index'])
        for shape in m['shapes']:
            if shape['kind'] == 'DATA':
                count = 0
                for field in m['nominal_fields']:
                    b.work()
                    if field['shape'] == shape['id']: count += 1
                vector(9,shape['id'],count)
        self.add_inventory('string-pool','pool/strings',len(self.pool),'byte.UTF8','UTF8Byte',1)
        self.add_inventory('header','header/program',1,'physical.RtProgram','ProgramHeader',1,mapping='packet-header')
        self.add_inventory('header','header/typed',1,'meta.TypedHeader','TypedHeader',2,mapping='packet-header')
        self.add_inventory('header','header/bindings',5,'byte.Digest32','Digest32',3,mapping='packet-header')
        # Canonical Stage03 order uses kind then lexical key. Sorting only keys
        # inside each fixed kind avoids relying on host dictionary insertion.
        b.creation()
        ordered = []
        for kind in ('table','vector','descriptor','index','string-pool','header'):
            keys = b.listing()
            for row in self.source_inventory:
                b.work()
                if row['kind'] == kind: b.append(keys,row['key'])
            for key in b.ordered(keys):
                obj = self.by_key[key]
                b.reserve(creation=10,work=1)
                row = b.row(id=len(ordered),kind=obj['source_kind'],key=key,count=obj['count'],
                            element_kind=obj['source_element_kind'],emission_status='planned-unbound')
                obj['source_id'] = len(ordered)
                b.append(ordered,row)
        same(m['storage_inventory'],ordered,'packet.storage_inventory',b)
        self.source_inventory = ordered
        b.work(len(ordered))
        if (m['counts']['storage_entries'] != len(ordered)
                or m['counts']['storage_objects'] != sum(row['count'] > 0 for row in ordered)):
            _error('packet.storage_inventory','INVENTORY','source storage counts differ')
        for key in ('header/program','header/typed','header/bindings'):
            b.append(self.objects,self.by_key[key])
        for index in range(len(ordered)-3):
            b.work()
            b.append(self.objects,self.by_key[ordered[index]['key']])
        b.reserve(creation=30,work=1)
        directory = b.row(source_id=None,key='packet/object-directory',source_kind=None,source_element_kind=None,
            kind=8,domain=1,owner=None,secondary_owner=None,element='ObjectDirectoryEntry',count=len(ordered)+1,
            rows=b.listing(),mapping_class='direct')
        b.append(self.objects,directory)
        b.put(self.by_key,'packet/object-directory',directory)
        for index,obj in enumerate(self.objects):
            b.put(obj,'directory_id',index)
        if len(self.objects) > LIMITS['directory_entries']:
            fail('packet.directory','packet-bounds','DIRECTORY_COUNT','directory exceeds packet subset')

    def span(self,key):
        b = self.budget
        b.reserve(creation=6,work=1)
        obj = self.by_key[key]
        return b.row(object=obj['directory_id'] if obj['count'] else NULL,count=obj['count'])

    def vkey(self,prefix,owner,secondary=None):
        b = self.budget
        uint(owner,'packet.vector.owner')
        b.creation(4)  # integer text and three concatenated string temporaries
        key = 'vector/' + prefix + '/' + str(owner)
        if secondary is not None:
            uint(secondary,'packet.vector.secondary_owner')
            b.creation(3); key += '/' + str(secondary)
        return key

    def reference(self,value,domain,path,nullable=False):
        if nullable and value is None: return NULL
        value = uint(value,path)
        if domain in _DOMAIN:
            count = len(self.metadata[_DOMAIN[domain]])
        elif domain == 'VariantSpec': count = len(self.variant_ids)
        else:
            _error(path,'REFERENCE','unknown reference domain')
        if value >= count:
            fail(path,'packet-schema','REFERENCE','reference is outside its exact domain')
        return value

    def value(self,value,kind,path):
        b = self.budget
        b.work()
        if kind.startswith('V<'):
            exact(value,('object','count'),path,b)
            obj, count = value['object'], value['count']
            uint(obj,path); uint(count,path)
            if count == 0:
                if obj != NULL: fail(path,'packet-schema','NULL_DOMAIN','empty span is not null')
            elif obj >= len(self.objects) or self.objects[obj]['count'] != count or self.objects[obj]['element'] != kind[2:-1]:
                fail(path,'packet-schema','REFERENCE','span differs from exact vector element/count')
            return value
        if kind in ('S','NS'):
            if kind == 'NS' and value is None: return NULL
            _name(value,path,b)
            if value not in self.strings:
                _error(path,'INVENTORY','string is missing from the exact pool')
            return self.strings[value]
        if kind.startswith('N<'): return self.reference(value,kind[2:-1],path,True)
        if kind.startswith('R<'): return self.reference(value,kind[2:-1],path)
        if '<' in kind:
            nullable = kind.startswith('NU')
            if nullable and value is None: return NULL
            enum = kind[kind.index('<')+1:-1]
            if enum in _TAGS:
                if type(value) is not str or value not in _TAGS[enum]:
                    fail(path,'packet-schema','TAG','unknown packet tag')
                return _TAGS[enum][value]
            if enum == 'ObjectDirectoryEntry':
                val = uint(value,path,nullable=nullable)
                if val >= len(self.objects): fail(path,'packet-schema','REFERENCE','directory object is absent')
                return val
            _error(path,'SCHEMA','unknown scalar domain')
        return uint(value,path,nullable=kind=='NU')

    def row(self,element,values,path):
        b = self.budget
        fields = _ELEMENT[element][2]
        b.creation(1 + len(fields))
        result = {}
        if type(values) is not dict:
            fail(path,'packet-schema','SCHEMA','mapped native row must be a dictionary')
        if len(values) != len(fields):
            fail(path,'packet-schema','SCHEMA','mapped native field count differs')
        for name,kind in fields:
            if name not in values:
                fail(path,'packet-schema','SCHEMA','mapped native field is missing')
            b.creation(3)  # bounded coordinate and schema-domain slices
            result[name] = self.value(values[name],kind,path+'.'+name)
        if 'expected_identity_flag' in result and result['expected_identity_flag'] not in (0,1):
            fail(path,'packet-schema','TAG','identity flag must be zero or one')
        _validate_null_domains(element,result,path,b)
        return result

    def append_row(self,key,element,values):
        obj = self.by_key[key]
        self.budget.work()
        if obj['element'] != element:
            _error('packet.objects','INVENTORY','object has wrong element type')
        if len(obj['rows']) >= obj['count']:
            _error('packet.objects','INVENTORY','object has more rows than inventory')
        self.budget.creation()  # mapped row coordinate before the call arguments
        self.budget.append(obj['rows'],self.row(element,values,'packet.'+key))

    def resolve_rep(self,ty,env):
        key = self.budget.pair(ty,env)
        self.budget.work()
        if key not in self.resolutions:
            _error('packet.descriptors','EQUATION','required exact representation resolution is absent')
        return self.resolutions[key]

    def tables(self):
        b,m = self.budget,self.metadata
        for table,element,_ in TABLES:
            for row in m[table]:
                b.reserve(creation=100,work=1)  # bounded per-row adaptation scratch
                values = dict(row)
                if table == 'environments':
                    values['arguments'] = self.span(self.vkey('env',row['id']))
                elif table == 'codes':
                    values['captures'] = self.span(self.vkey('code-captures',row['id']))
                    values['body_path'] = _path_text(row['body_path'],b)
                elif table == 'code_executions':
                    values['captures'] = self.span(self.vkey('execution-captures',row['id']))
                elif table == 'shapes':
                    source = values.pop('source'); tag = source['kind']
                    exact(source,('kind','reference') if tag=='legacy' else ('kind','type') if tag=='canonical-arrow' else ('kind','type','scheme'), 'packet.shapes.source',b)
                    values.update(source_tag=tag,source_reference=source.get('reference'),source_type=source.get('type'),source_scheme=source.get('scheme'))
                elif table == 'families':
                    values['variants'] = self.span(self.vkey('family-variants',row['id']))
                elif table == 'sites':
                    context = values.pop('context'); tag = context['kind']
                    exact(context,('kind',) if tag=='concrete' else ('kind','intro') if tag=='introduction' else ('kind','code','scheme'),'packet.sites.context',b)
                    values.update(path=_path_text(row['path'],b),context_tag=tag,context_intro=context.get('intro'),context_code=context.get('code'),context_scheme=context.get('scheme'))
                    supplement = self.supplement['sites'][row['id']]
                    values.update(sum_family=supplement['sum_family'],sum_variant=supplement['sum_variant'])
                elif table == 'slots':
                    role = values.pop('role'); tag = role['kind']
                    exact(role,('kind','name') if tag=='capture' else ('kind','field') if tag=='field' else ('kind','variant','field') if tag=='variant-field' else ('kind',),'packet.slots.role',b)
                    values.update(role_tag=tag,role_name=role.get('name'),role_variant=role.get('variant'),role_field=role.get('field'))
                elif table == 'introductions':
                    container = values.pop('container'); tag = container['kind']
                    exact(container,('kind',) if tag=='entry' else ('kind','code'),'packet.introductions.container',b)
                    values.update(container_tag=tag,container_code=container.get('code'),generalize_path=_path_text(row['generalize_path'],b),seal_path=_path_text(row['seal_path'],b),result_sites=self.span(self.vkey('intro-sites',row['id'])))
                elif table == 'uses':
                    same(row['arguments'],m['environments'][row['env']]['arguments'],'packet.uses.arguments',b)
                    values['arguments'] = self.span(self.vkey('env',row['env']))
                    values['occurrences'] = self.span(self.vkey('use-occurrences',row['id']))
                self.append_row('table/'+table,element,values)

    def vectors(self):
        b,m = self.budget,self.metadata
        for env in m['environments']:
            for ty in env['arguments']:
                b.creation(4); self.append_row(self.vkey('env',env['id']),'TypeRef',{'row':ty})
        for code in m['codes']:
            for capture in code['captures']:
                exact(capture,('name','type','relation'),'packet.captures',b)
                self.append_row(self.vkey('code-captures',code['id']),'CaptureTyping',capture)
        for execution in m['code_executions']:
            captures=m['codes'][execution['code']]['captures']
            if len(captures)!=len(execution['captures']): _error('packet.captures','EQUATION','resolved capture count differs')
            for position,capture in enumerate(execution['captures']):
                b.reserve(creation=10,work=1)
                exact(capture,('name','type','relation'),'packet.resolved-captures',b)
                if capture['name']!=captures[position]['name'] or capture['relation']!=captures[position]['relation']:
                    _error('packet.captures','EQUATION','shared capture name/relation differs')
                self.append_row(self.vkey('execution-captures',execution['id']),'ResolvedCapture',{'code':execution['code'],'position':position,'type':capture['type']})
        for intro in m['introductions']:
            for site in intro['result_sites']:
                b.creation(4); self.append_row(self.vkey('intro-sites',intro['id']),'SiteRef',{'row':site})
        for use in m['uses']:
            for path in use['occurrences']:
                b.creation(4); self.append_row(self.vkey('use-occurrences',use['id']),'PathRef',{'path':_path_text(path,b)})
        for family in m['families']:
            for variant in family['variants']:
                b.reserve(creation=12,work=1)
                exact(variant,('name','index','fields'),'packet.variants',b)
                self.append_row(self.vkey('family-variants',family['id']),'VariantTyping',{'name':variant['name'],'index':variant['index'],'fields':self.span(self.vkey('variant-fields',family['id'],variant['index']))})
                self.append_row(self.vkey('family-variant-pointers',family['id']),'VariantRef',{'row':self.variant_ids[b.pair(family['id'],variant['index'])]})
                for field in variant['fields']:
                    b.creation(4); self.append_row(self.vkey('variant-fields',family['id'],variant['index']),'NominalFieldRef',{'row':field})
        for shape in m['shapes']:
            if shape['kind']=='DATA':
                for field in m['nominal_fields']:
                    b.work()
                    if field['shape']==shape['id']:
                        b.creation(4); self.append_row(self.vkey('data-fields',shape['id']),'NominalFieldRef',{'row':field['id']})

    def field_slice(self,shape,variant):
        b,m=self.budget,self.metadata
        first=count=0
        for field in m['nominal_fields']:
            b.work()
            if field['shape']==shape and field['variant']==variant:
                if count==0: first=field['id']
                elif field['id']!=first+count: _error('packet.fields','EQUATION','nominal field slice is not contiguous')
                count+=1
        b.creation(4)
        return (self.by_key['descriptor/nominal-fields']['directory_id'] if count else None,first,count)

    def descriptors(self):
        b,m=self.budget,self.metadata
        for shape in m['shapes']:
            b.reserve(creation=30,work=1)
            obj,first,count=self.field_slice(shape['id'],None) if shape['kind']=='DATA' else (None,0,0)
            self.append_row('descriptor/shapes','ShapeSpec',{'shape':shape['id'],'typing':shape['id'],'representation':shape['id'],'kind':shape['kind'],'fields_object':obj,'field_first':first,'field_count':count,'argument_rep':shape['argument_rep'],'result_rep':shape['result_rep']})
        capture_first=0
        for code in m['codes']:
            b.reserve(creation=30,work=1)
            env=0 if code['scope'] is None else m['schemes'][code['scope']]['neutral_env']
            principal=code['callable_type'] if code['kind']=='function' else code['result']
            count=len(code['captures'])
            self.append_row('descriptor/codes','CodeSpec',{'code':code['id'],'principal_env':env,'principal_rep':self.resolve_rep(principal,env),'capture_object':self.by_key['descriptor/code-capture-fields']['directory_id'] if count else None,'capture_first':capture_first if count else 0,'capture_count':count,'body_binding':'UNBOUND'})
            for position,capture in enumerate(code['captures']):
                b.reserve(creation=24,work=1)
                self.append_row('descriptor/code-capture-fields','FieldSpec',{'owner_kind':'code','owner':code['id'],'position':position,'name':capture['name'],'type':capture['type'],'nominal_declared_rep':None,'code_principal_rep':self.resolve_rep(capture['type'],env),'relation':capture['relation']})
            capture_first+=count
        for family in m['families']:
            b.reserve(creation=12,work=1)
            self.append_row('descriptor/families','FamilySpec',{'family':family['id'],'shape':family['shape'],'variants':self.span(self.vkey('family-variant-pointers',family['id']))})
            for variant in family['variants']:
                b.reserve(creation=24,work=1)
                obj,first,count=self.field_slice(family['shape'],variant['index'])
                self.append_row('descriptor/variants','VariantSpec',{'family':family['id'],'index':variant['index'],'name':variant['name'],'shape':family['shape'],'fields_object':obj,'field_first':first,'field_count':count})
        for field in m['nominal_fields']:
            b.reserve(creation=24,work=1)
            owner,kind=field['shape'],'data'
            if field['variant'] is not None:
                kind='variant'; owner=None
                for family in m['families']:
                    b.work()
                    if family['shape']==field['shape']:
                        if owner is not None: _error('packet.fields','EQUATION','field family is ambiguous')
                        owner=self.variant_ids[b.pair(family['id'],field['variant'])]
                if owner is None: _error('packet.fields','EQUATION','field family is absent')
            self.append_row('descriptor/nominal-fields','FieldSpec',{'owner_kind':kind,'owner':owner,'position':field['position'],'name':field['name'],'type':field['type'],'nominal_declared_rep':field['declared_rep'],'code_principal_rep':None,'relation':None})

    def finish(self):
        b,m=self.budget,self.metadata
        self.tables(); self.vectors(); self.descriptors()
        for obj in self.objects:
            if obj['kind'] in (2,4):
                for index in range(obj['count']):
                    b.reserve(creation=8,work=1)
                    # Registry domain IDs are numeric U values, not enum spellings.
                    b.append(obj['rows'],b.row(domain=obj['domain'],row=index))
        self.by_key['pool/strings']['rows']=self.pool
        for digest in self.bindings:
            if type(digest) is not str or len(digest)!=64 or any(char not in '0123456789abcdef' for char in digest):
                fail('packet.bindings','packet-schema','SCHEMA','binding is not exact lowercase SHA256')
            b.reserve(creation=34,work=64)
            values=list(bytes.fromhex(digest))
            b.reserve(creation=4,work=1)
            b.append(self.by_key['header/bindings']['rows'],b.row(bytes=values))
        # Header/directory rows have dedicated compiler-expression templates.
        # Empty rows in these three objects are intentional, not missing C rows.
        for obj in self.objects:
            b.work()
            if obj['element'] not in ('ProgramHeader','TypedHeader','ObjectDirectoryEntry') and len(obj['rows'])!=obj['count']:
                _error('packet.objects','INVENTORY','emitted row count differs from source inventory')
        total=0
        for table in ('type_resolutions','representation_resolutions','accesses','transports'):
            b.work(); total+=len(m[table])
        if total>LIMITS['R'] or total!=m['counts']['access_transport_resolution_rows']:
            _error('packet.rows','EQUATION','actual resolution/Access/transport lengths differ')
        b.reserve(creation=12,work=1)
        return b.row(format='resource-ir-v8-c-packet-specification/1',bindings=b.listing(self.bindings),
                     supplement=self.supplement,objects=self.objects,resolution_access_transport_rows=total)


def derive_specification(raw,metadata,bindings,budget):
    return Projection(raw,metadata,bindings,budget).finish()


def _validate_null_domains(element,row,path,budget):
    """Check tag-dependent payload domains in addition to scalar membership."""
    budget.reserve(creation=8,work=1)
    def nulls(names):
        for name in names:
            budget.work()
            if row[name]!=NULL: fail(path+'.'+name,'packet-schema','NULL_DOMAIN','inapplicable payload must be null')
    def present(names):
        for name in names:
            budget.work()
            if row[name]==NULL: fail(path+'.'+name,'packet-schema','NULL_DOMAIN','required payload is null')
    if element=='Type':
        if row['tag']==1:
            present(('atom',)); nulls(('scheme','index','argument','result','protocol','result_identity'))
        elif row['tag']==2:
            present(('scheme','index')); nulls(('atom','argument','result','protocol','result_identity'))
        else:
            present(('argument','result','protocol','result_identity')); nulls(('atom','scheme','index'))
    elif element=='Env':
        if row['mode']==1:
            nulls(('scheme',))
            if row['id']!=0 or row['arguments']['count']!=0:
                fail(path,'packet-schema','NULL_DOMAIN','concrete environment must be empty E0')
        else: present(('scheme',))
    elif element=='CodeTyping':
        if row['kind']==1: present(('callable_type','argument','expected_protocol'))
        else:
            nulls(('callable_type','argument','expected_protocol'))
            if row['expected_identity_flag']!=0: fail(path,'packet-schema','TAG','thunk identity flag must be zero')
    elif element=='ShapeBinding':
        if row['source_tag']==1:
            present(('source_reference',)); nulls(('source_type','source_scheme'))
        elif row['source_tag']==2:
            present(('source_type',)); nulls(('source_reference','source_scheme'))
        else:
            present(('source_type','source_scheme')); nulls(('source_reference',))
        if row['kind']==5: present(('argument_rep','result_rep'))
        else: nulls(('argument_rep','result_rep'))
    elif element=='Site':
        if row['category']==7: present(('sum_family','sum_variant'))
        else: nulls(('sum_family','sum_variant'))
        if row['category'] in (2,3): present(('code',))
        else: nulls(('code',))
        if row['category']!=3: nulls(('arm',))
        if row['context_tag']==1: nulls(('context_intro','context_code','context_scheme'))
        elif row['context_tag']==2:
            present(('context_intro',)); nulls(('context_code','context_scheme'))
        else:
            present(('context_code','context_scheme')); nulls(('context_intro',))
    elif element=='Slot':
        if row['role_tag']==1:
            present(('role_name',)); nulls(('role_variant','role_field'))
        elif row['role_tag']==2:
            present(('role_field',)); nulls(('role_name','role_variant'))
        elif row['role_tag']==3:
            present(('role_variant','role_field')); nulls(('role_name',))
        else: nulls(('role_name','role_variant','role_field'))
    elif element=='Access':
        if row['mode']==1:
            present(('use_env',)); nulls(('scheme',))
        else:
            present(('scheme',)); nulls(('use_env',))
    elif element=='Intro':
        if row['container_tag']==1: nulls(('container_code',))
        else: present(('container_code',))
    elif element=='Transport':
        if row['kind']==1: nulls(('projection_env',))
        else: present(('projection_env',))
    elif element=='FieldSpec':
        if row['owner_kind']==3:
            present(('code_principal_rep','relation')); nulls(('nominal_declared_rep',))
        else:
            present(('nominal_declared_rep',)); nulls(('code_principal_rep','relation'))
    elif element in ('ShapeSpec','VariantSpec','CodeSpec'):
        prefix='capture' if element=='CodeSpec' else 'field'
        obj='capture_object' if element=='CodeSpec' else 'fields_object'
        if row[prefix+'_count']==0:
            nulls((obj,))
            if row[prefix+'_first']!=0: fail(path,'packet-schema','NULL_DOMAIN','empty descriptor slice must start at zero')
        else: present((obj,))


def _c_uint(writer,value):
    writer.emit(b'UINT32_C('); writer.number(value); writer.emit(b')')


def _c_bytes(writer,values):
    writer.emit(b'{')
    for index,value in enumerate(values):
        writer.budget.work()
        if type(value) is not int or not 0<=value<=255:
            fail('packet.source.bytes','packet-source','SOURCE_GRAMMAR','non-byte initializer')
        if index: writer.emit(b',')
        writer.number(value)
    writer.emit(b'}')


def _c_span(writer,span):
    exact(span,('object','count'),'packet.source.span',writer.budget)
    writer.emit(b'{'); _c_uint(writer,span['object']); writer.emit(b','); _c_uint(writer,span['count']); writer.emit(b'}')


def _c_row(writer,element,row):
    fields=_ELEMENT[element][2]
    writer.emit(b'{')
    for index,(name,kind) in enumerate(fields):
        writer.budget.work()
        if index: writer.emit(b',')
        writer.emit(b'.'); writer.ascii(name); writer.emit(b'=')
        if kind.startswith('V<'): _c_span(writer,row[name])
        elif kind=='unsigned-char[32]': _c_bytes(writer,row[name])
        else: _c_uint(writer,row[name])
    writer.emit(b'}')


def _member(writer,obj):
    writer.emit(b'o'); writer.number(obj['directory_id'])


def _sizeof_member(writer,obj):
    writer.emit(b'sizeof((('); writer.ascii(ROOT_TYPE); writer.emit(b' *)0)->')
    _member(writer,obj); writer.emit(b')')


def _offsetof_member(writer,obj):
    writer.emit(b'offsetof('); writer.ascii(ROOT_TYPE); writer.emit(b',')
    _member(writer,obj); writer.emit(b')')


def _element_measure(writer,obj,operator):
    writer.ascii(operator); writer.emit(b'(')
    writer.ascii(_ELEMENT[obj['element']][0]); writer.emit(b')')


def _render_program(writer,spec,by_key):
    writer.emit(b'{{.magic='); _c_bytes(writer,(73,82,56,80,75,84,48,49))
    writer.emit(b',.abi_revision=UINT32_C(1),.purpose=UINT32_C(1),.packet_bytes=sizeof(')
    writer.ascii(ROOT_TYPE); writer.emit(b'),.packet_alignment=_Alignof('); writer.ascii(ROOT_TYPE)
    writer.emit(b'),.directory_offset='); _offsetof_member(writer,by_key['packet/object-directory'])
    writer.emit(b',.directory_count='); _c_uint(writer,len(spec['objects']))
    writer.emit(b',.typed_header_object='); _c_uint(writer,by_key['header/typed']['directory_id'])
    writer.emit(b',.bindings_object='); _c_uint(writer,by_key['header/bindings']['directory_id'])
    writer.emit(b',.string_pool_object=')
    pool=by_key['pool/strings']; _c_uint(writer,pool['directory_id'] if pool['count'] else NULL)
    writer.emit(b',.resolution_access_transport_rows='); _c_uint(writer,spec['resolution_access_transport_rows'])
    writer.emit(b'}}')


def _render_typed(writer,by_key):
    writer.emit(b'{{')
    writer.budget.creation(21)  # outer tuple and four three-member tuple records
    for field,prefix,domains in (('table','table/',TABLES),('table_index','index/table/',TABLES),
                               ('descriptor','descriptor/',DESCRIPTORS),('descriptor_index','index/descriptor/',DESCRIPTORS)):
        if field!='table': writer.emit(b',')
        writer.emit(b'.'); writer.ascii(field); writer.emit(b'={')
        for index,domain in enumerate(domains):
            if index: writer.emit(b',')
            writer.budget.creation()  # exact inventory-key concatenation
            obj=by_key[prefix+domain[0]]
            writer.emit(b'{'); _c_uint(writer,obj['directory_id'] if obj['count'] else NULL)
            writer.emit(b','); _c_uint(writer,obj['count']); writer.emit(b'}')
        writer.emit(b'}')
    writer.emit(b'}}')


def _render_directory(writer,spec):
    writer.emit(b'{\n')
    for index,obj in enumerate(spec['objects']):
        writer.budget.work()
        if index: writer.emit(b',\n')
        writer.emit(b'{.source_inventory_id='); _c_uint(writer,NULL if obj['source_id'] is None else obj['source_id'])
        writer.emit(b',.kind='); _c_uint(writer,obj['kind'])
        writer.emit(b',.domain_or_subkind='); _c_uint(writer,obj['domain'])
        writer.emit(b',.owner='); _c_uint(writer,NULL if obj['owner'] is None else obj['owner'])
        writer.emit(b',.secondary_owner='); _c_uint(writer,NULL if obj['secondary_owner'] is None else obj['secondary_owner'])
        writer.emit(b',.element_type='); _c_uint(writer,_ELEMENT[obj['element']][1])
        writer.emit(b',.offset=')
        if obj['count']: _offsetof_member(writer,obj)
        else: _c_uint(writer,NULL)
        writer.emit(b',.count='); _c_uint(writer,obj['count'])
        writer.emit(b',.element_bytes='); _element_measure(writer,obj,'sizeof')
        writer.emit(b',.element_alignment='); _element_measure(writer,obj,'_Alignof')
        writer.emit(b',.object_bytes=')
        if obj['count']: _sizeof_member(writer,obj)
        else: _c_uint(writer,0)
        writer.emit(b'}')
    writer.emit(b'\n}')


def render_source(spec,budget):
    """Fixed templates only. No filenames, source fragments or flags from IR."""
    budget.reserve(creation=2+len(spec['objects']),work=len(spec['objects']))
    by_key={obj['key']:obj for obj in spec['objects']}
    header=Writer(budget,'source',LIMITS['production_source_bytes'])
    header.emit(b'#ifndef IR8_PACKET_GENERATED_H\n#define IR8_PACKET_GENERATED_H\n#include "ir8_packet.h"\n')
    header.ascii(ROOT_TYPE); header.emit(b' {\n')
    for obj in spec['objects']:
        budget.work()
        if obj['count']:
            header.emit(b'    '); header.ascii(_ELEMENT[obj['element']][0]); header.emit(b' ')
            _member(header,obj); header.emit(b'['); header.number(obj['count']); header.emit(b'];\n')
    header.emit(b'};\nconst void *ir8_packet_generated_data(void);\nsize_t ir8_packet_generated_size(void);\n#endif\n')
    header_text,header_hash,header_bytes=header.finish()
    source=Writer(budget,'source',LIMITS['production_source_bytes'])
    source.emit(b'#include "ir8_packet_generated.h"\n')
    source.emit(b'_Static_assert(sizeof('); source.ascii(ROOT_TYPE)
    source.emit(b') <= UINT32_C(4194304), "packet byte limit");\n')
    source.emit(b'_Static_assert(_Alignof('); source.ascii(ROOT_TYPE)
    source.emit(b') <= UINT32_MAX, "packet alignment width");\n')
    source.emit(b'_Static_assert(offsetof('); source.ascii(ROOT_TYPE)
    source.emit(b',o0) == 0, "program header first");\n')
    # Compiler expressions, not host estimates, establish all stored widths.
    for obj in spec['objects']:
        budget.work()
        source.emit(b'_Static_assert('); _element_measure(source,obj,'sizeof')
        source.emit(b' <= UINT32_MAX && '); _element_measure(source,obj,'_Alignof')
        source.emit(b' <= UINT32_MAX, "element measurement width");\n')
        if obj['count']:
            source.emit(b'_Static_assert('); _offsetof_member(source,obj)
            source.emit(b' <= UINT32_MAX && '); _sizeof_member(source,obj)
            source.emit(b' <= UINT32_MAX, "member measurement width");\n')
    source.emit(b'static const '); source.ascii(ROOT_TYPE); source.emit(b' ')
    source.ascii(ROOT_SYMBOL); source.emit(b' = {\n')
    first=True
    for obj in spec['objects']:
        budget.work()
        if not obj['count']: continue
        if not first: source.emit(b',\n')
        first=False
        source.emit(b'.'); _member(source,obj); source.emit(b'=')
        if obj['element']=='ProgramHeader': _render_program(source,spec,by_key)
        elif obj['element']=='TypedHeader': _render_typed(source,by_key)
        elif obj['element']=='ObjectDirectoryEntry': _render_directory(source,spec)
        elif obj['element']=='UTF8Byte': _c_bytes(source,obj['rows'])
        else:
            source.emit(b'{\n')
            for index,row in enumerate(obj['rows']):
                if index: source.emit(b',\n')
                _c_row(source,obj['element'],row)
            source.emit(b'\n}')
    source.emit(b'\n};\nconst void *ir8_packet_generated_data(void) { return &')
    source.ascii(ROOT_SYMBOL); source.emit(b'; }\nsize_t ir8_packet_generated_size(void) { return sizeof(')
    source.ascii(ROOT_SYMBOL); source.emit(b'); }\n')
    source_text,source_hash,source_bytes=source.finish()
    budget.creation(7)
    return header_text,source_text,header_hash,source_hash,header_bytes,source_bytes


def verify_lossless(metadata,spec,budget):
    """Reverse the complete native table projection and compare every field.

    This is an emitter-internal losslessness check, not the independent native
    readback oracle. It cannot create or cache any checker/execution authority.
    """
    from .packet_budget import decode_fresh
    budget.reserve(creation=3+len(spec['objects']),work=len(spec['objects']))
    objects={obj['key']:obj for obj in spec['objects']}
    pool=objects['pool/strings']['rows']
    budget.creation()
    strings={}
    start=0
    while start<len(pool):
        end=start
        while end<len(pool) and pool[end]!=0:
            budget.work(); end+=1
        if end==len(pool): _error('packet.pool','INVENTORY','unterminated pool string')
        budget.reserve(creation=3+end-start,work=end-start)
        text=bytes(pool[start:end]).decode('utf-8','strict')
        budget.put(strings,start,text)
        start=end+1
    def string(offset,optional=False):
        uint(offset,'packet.mapping.string')
        if optional and offset==NULL: return None
        if offset not in strings: _error('packet.mapping.string','REFERENCE','offset is not a pool start')
        return strings[offset]
    def row(element,source):
        fields=_ELEMENT[element][2]
        budget.creation(1+len(fields))
        result={}
        for name,kind in fields:
            budget.work()
            value=source[name]
            if kind in ('S','NS'): value=string(value,kind=='NS')
            elif kind.startswith('V<'): pass
            elif kind.startswith('NU') or kind.startswith('N<'):
                if value==NULL: value=None
            if value is not None and '<' in kind and not kind.startswith(('V<','R<','N<')):
                budget.creation()  # enum-domain substring before construction
                enum=kind[kind.index('<')+1:-1]
                if enum in _TAGS:
                    found=None
                    for key,number in _TAGS[enum].items():
                        budget.work()
                        if number==value: found=key
                    if found is None: _error('packet.mapping.tag','TAG','unrecognized stored tag')
                    value=found
            result[name]=value
        return result
    def vector(span,key):
        obj=objects[key]
        budget.work()
        if span['count']!=obj['count'] or span['object']!=(obj['directory_id'] if obj['count'] else NULL):
            _error('packet.mapping.vector','INVENTORY','span does not reference its exact owner object')
        return obj['rows']
    def ids(span,key):
        rows=vector(span,key)
        budget.reserve(creation=1+len(rows),work=len(rows))
        return [value['row'] for value in rows]
    def key(prefix,owner,secondary=None):
        budget.creation(4)
        value='vector/'+prefix+'/'+str(owner)
        if secondary is not None:
            budget.creation(3); value+='/'+str(secondary)
        return value
    for table,element,_ in TABLES:
        budget.creation()  # reverse-projection table key before lookup
        native=objects['table/'+table]['rows']
        if len(native)!=len(metadata[table]): _error('packet.mapping.'+table,'INVENTORY','table row count differs')
        for index,stored in enumerate(native):
            budget.reserve(creation=100,work=1)
            value=row(element,stored)
            if table=='environments': value['arguments']=ids(value['arguments'],key('env',index))
            elif table=='codes':
                values=vector(value['captures'],key('code-captures',index))
                result=budget.listing()
                for capture in values: budget.append(result,row('CaptureTyping',capture))
                value['captures']=result
                value['body_path']=decode_fresh(value['body_path'],budget)
            elif table=='code_executions':
                captures=vector(value['captures'],key('execution-captures',index))
                code=objects['table/codes']['rows'][value['code']]
                declarations=vector(code['captures'],key('code-captures',value['code']))
                result=budget.listing()
                for position,capture in enumerate(captures):
                    budget.reserve(creation=10,work=1)
                    if capture['code']!=value['code'] or capture['position']!=position or position>=len(declarations):
                        _error('packet.mapping.captures','EQUATION','resolved capture sharing differs')
                    declaration=row('CaptureTyping',declarations[position])
                    budget.append(result,budget.row(name=declaration['name'],type=capture['type'],relation=declaration['relation']))
                if len(captures)!=len(declarations): _error('packet.mapping.captures','EQUATION','capture cardinality differs')
                value['captures']=result
            elif table=='shapes':
                tag=value.pop('source_tag'); reference=value.pop('source_reference')
                ty=value.pop('source_type'); scheme=value.pop('source_scheme')
                if tag=='legacy':
                    if ty is not None or scheme is not None: _error('packet.mapping.shapes','NULL_DOMAIN','unexpected legacy payload')
                    value['source']=budget.row(kind=tag,reference=reference)
                elif tag=='canonical-arrow':
                    if reference is not None or scheme is not None: _error('packet.mapping.shapes','NULL_DOMAIN','unexpected arrow payload')
                    value['source']=budget.row(kind=tag,type=ty)
                else:
                    if reference is not None: _error('packet.mapping.shapes','NULL_DOMAIN','unexpected OPEN payload')
                    value['source']=budget.row(kind=tag,type=ty,scheme=scheme)
            elif table=='families':
                variants=vector(value['variants'],key('family-variants',index))
                result=budget.listing()
                for variant in variants:
                    item=row('VariantTyping',variant)
                    item['fields']=ids(item['fields'],key('variant-fields',index,item['index']))
                    budget.append(result,item)
                value['variants']=result
            elif table=='sites':
                value['path']=decode_fresh(value['path'],budget)
                family=value.pop('sum_family'); variant=value.pop('sum_variant')
                expected=spec['supplement']['sites'][index]
                if (family!=expected['sum_family'] or variant!=expected['sum_variant']
                        or (value['category']=='SUM')!=(family is not None and variant is not None)):
                    _error('packet.mapping.sites','SUPPLEMENT','selected SUM supplement differs')
                tag=value.pop('context_tag'); intro=value.pop('context_intro')
                code=value.pop('context_code'); scheme=value.pop('context_scheme')
                if tag=='concrete':
                    if any(item is not None for item in (intro,code,scheme)): _error('packet.mapping.sites','NULL_DOMAIN','concrete context payload')
                    context=budget.row(kind=tag)
                elif tag=='introduction':
                    if code is not None or scheme is not None: _error('packet.mapping.sites','NULL_DOMAIN','introduction context payload')
                    context=budget.row(kind=tag,intro=intro)
                else:
                    if intro is not None: _error('packet.mapping.sites','NULL_DOMAIN','execution context payload')
                    context=budget.row(kind=tag,code=code,scheme=scheme)
                value['context']=context
            elif table=='slots':
                tag=value.pop('role_tag'); name=value.pop('role_name')
                variant=value.pop('role_variant'); field=value.pop('role_field')
                if tag=='capture':
                    if variant is not None or field is not None: _error('packet.mapping.slots','NULL_DOMAIN','capture role payload')
                    role=budget.row(kind=tag,name=name)
                elif tag=='field':
                    if name is not None or variant is not None: _error('packet.mapping.slots','NULL_DOMAIN','field role payload')
                    role=budget.row(kind=tag,field=field)
                elif tag=='variant-field':
                    if name is not None: _error('packet.mapping.slots','NULL_DOMAIN','variant role payload')
                    role=budget.row(kind=tag,variant=variant,field=field)
                else:
                    if any(item is not None for item in (name,variant,field)): _error('packet.mapping.slots','NULL_DOMAIN','scalar role payload')
                    role=budget.row(kind=tag)
                value['role']=role
            elif table=='introductions':
                tag=value.pop('container_tag'); code=value.pop('container_code')
                if tag=='entry':
                    if code is not None: _error('packet.mapping.introductions','NULL_DOMAIN','entry container code')
                    value['container']=budget.row(kind=tag)
                else: value['container']=budget.row(kind=tag,code=code)
                value['generalize_path']=decode_fresh(value['generalize_path'],budget)
                value['seal_path']=decode_fresh(value['seal_path'],budget)
                value['result_sites']=ids(value['result_sites'],key('intro-sites',index))
            elif table=='uses':
                value['arguments']=ids(value['arguments'],key('env',value['env']))
                occurrences=vector(value['occurrences'],key('use-occurrences',index))
                result=budget.listing()
                for occurrence in occurrences:
                    budget.append(result,decode_fresh(string(occurrence['path']),budget))
                value['occurrences']=result
            same(value,metadata[table][index],'packet.mapping.'+table,budget)
