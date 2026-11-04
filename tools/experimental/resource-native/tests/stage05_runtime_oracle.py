"""Independent raw/resource/metadata correspondence for a restricted C template.

No executable producer lowering is imported. C is parsed as data, never run.
This is deliberately not a general C syntax checker or a runtime proof.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from types import SimpleNamespace

ABI_SHA256 = 'c6e3a34ea54b7f7224f94ece8a24a821d74e32d60db0a0fb16933252a2623500'
PACKET_SCHEMA_SHA256 = 'e4976fb839a8b738c0797100fe7b5d1fc948f2b995ab17f3c44cc8cc4fb94ba6'
FIELDS = ('format', 'canonical_ir_json', 'packet_manifest_json', 'metadata_json',
          'runtime_header', 'runtime_source', 'packet_header', 'packet_source',
          'manifest_json', 'manifest_sha256', 'statistics')
OUTPUTS = ('packet_header', 'packet_source', 'runtime_header', 'runtime_source')
LIMITS = dict(creation_units=2097152, work_units=16777216, source_utf8_bytes=33554432,
              manifest_utf8_bytes=8388608, label_utf8_bytes=1048576, label_count=65536,
              source_chunk_bytes=4096, frame_pointer_cells=512, typed_static_bytes=4194304,
              owned_json_depth=64)
# Independent declarative instruction/ABI table, not producer executable data.
HELPERS = {x: 'rt8_' + x for x in (
    'new_root', 'new_below', 'alloc', 'closure', 'thunk', 'hole', 'application',
    'application_borrow', 'fill', 'borrow', 'end_borrow', 'retain', 'drop', 'field',
    'force', 'return', 'prim2', 'finish_scalar', 'select_i64', 'construct_nullary',
    'construct_sum', 'case_i64', 'case_fields_i64', 'instantiate')}
HELPERS.update(finish='rt8_finish_entry', generalize='rt8_generic_begin', seal='rt8_generic_seal')
ALLOC = frozenset(('alloc', 'closure', 'thunk', 'hole', 'application',
                  'application_borrow', 'scalar', 'prim2', 'construct_nullary', 'construct_sum'))
LABELLED = ALLOC | {'field', 'force', 'select_i64', 'case_i64', 'case_fields_i64', 'instantiate'}
ACCESSORS = {'rt8_site': 'const Rt8Site *', 'rt8_code': 'const Rt8Code *',
             'rt8_intro': 'const Rt8Intro *', 'rt8_instantiation': 'const Rt8Instantiation *',
             'rt8_family': 'const Rt8Family *', 'rt8_variant': 'const Rt8Variant *',
             'rt8_site_shape': 'const Rt8Shape *', 'rt8_shape': 'const Rt8Shape *',
             'rt8_env': 'const Rt8Env *', 'rt8_label': 'const char *'}
PRIMITIVES = {'addInt': 'RT8_PRIM_ADD_INT', 'subInt': 'RT8_PRIM_SUB_INT',
              'mulInt': 'RT8_PRIM_MUL_INT', 'eqInt': 'RT8_PRIM_EQ_INT', 'ltInt': 'RT8_PRIM_LT_INT'}


class OracleError(ValueError):
    def __init__(self, code, message):
        self.code = code
        self.layer = 'stage05-source-oracle'
        self.path = 'oracle.' + code[2:].lower()
        self.message = message
        super().__init__(self.path + ': ' + code + ': ' + message)


def need(ok, code, message):
    if not ok:
        raise OracleError(code, message)


def sha(text):
    data = text.encode('utf-8') if type(text) is str else text
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def pin(text):
    data = text.encode('utf-8') if type(text) is str else text
    return {'bytes': len(data), 'sha256': sha(data)}


def equal(a, b, code, message):
    if type(a) is not type(b):
        raise OracleError(code, message + ': exact type differs')
    if isinstance(a, dict):
        need(a.keys() == b.keys(), code, message + ': keys differ')
        for key in a:
            equal(a[key], b[key], code, message + '/' + str(key))
    elif isinstance(a, (tuple, list)):
        need(len(a) == len(b), code, message + ': length differs')
        for index, (left, right) in enumerate(zip(a, b)):
            equal(left, right, code, message + '/' + str(index))
    else:
        need(a == b, code, message)


def keys(value, expected, code='O_SCHEMA'):
    need(type(value) is dict and set(value) == set(expected), code, 'exact record keys differ')


def nonnegative(value, limit=4294967295, code='O_SCHEMA'):
    need(type(value) is int and 0 <= value <= limit, code, 'plain unsigned count/index required')


def typed(value):
    """Evidence tagged values preserve every scalar/container type."""
    if value is None:
        return {'type': 'null', 'value': None}
    if type(value) in (str, int, bool):
        return {'type': type(value).__name__, 'value': value}
    if type(value) in (tuple, list):
        return {'type': type(value).__name__, 'value': [typed(x) for x in value]}
    if type(value) is dict:
        need(all(type(k) is str for k in value), 'O_SCHEMA', 'typed dictionary keys')
        return {'type': 'dict', 'value': {k: typed(v) for k, v in value.items()}}
    raise OracleError('O_SCHEMA', 'unsupported evidence value type')


def pathkey(path):
    keys(path, ('root', 'name', 'segments'), 'O_PATH')
    need(path['root'] in ('entry', 'function', 'thunk'), 'O_PATH', 'path root')
    need((path['name'] is None) == (path['root'] == 'entry'), 'O_PATH', 'path name domain')
    need(type(path['segments']) is list, 'O_PATH', 'path segments')
    for x in path['segments']:
        need((type(x) is int and x >= 0) or (type(x) is str and x == 'body'), 'O_PATH', 'path segment')
    return path['root'], path['name'], tuple(path['segments'])


def raw_at(raw, path):
    bank = raw['entry'] if path['root'] == 'entry' else raw['functions' if path['root'] == 'function' else 'codes'][path['name']]['body']
    for segment in path['segments']:
        bank = bank[segment]
    return bank


def walk(body, root, name, prefix=()):
    for index, inst in enumerate(body):
        path = dict(root=root, name=name, segments=list(prefix + (index,)))
        yield path, inst
        if inst['op'] == 'generalize':
            yield from walk(inst['body'], root, name, prefix + (index, 'body'))


def operand(inst, role):
    value = inst
    for part in role:
        value = value[part]
    need(type(value) is str, 'O_OPERAND', 'resource role does not denote raw name')
    return value


def roles_for(inst, raw, codes):
    """Raw syntax roles, independently matched to every resource fact."""
    op = inst['op']
    result = []
    if op in ('new_root', 'new_below'):
        if op == 'new_below': result.append(['ceiling'])
        result += [['imports', i] for i in range(len(inst['imports']))]
        return result
    if op in ALLOC | {'select_i64', 'case_i64', 'case_fields_i64', 'generalize'}:
        result.append(['in'])
        if op == 'alloc': result += [['fields', k] for k in sorted(inst['fields'])]
        elif op in ('closure', 'thunk'):
            kind = 'function' if op == 'closure' else 'thunk'
            code = codes[(kind, inst['function' if kind == 'function' else 'code'])]
            result += [['captures', x['name']] for x in code['captures']]
        elif op in ('application', 'application_borrow'):
            result += [['function'], ['argument']]
        elif op == 'prim2': result += [['left'], ['right']]
        elif op == 'construct_sum': result += [['fields', i] for i in range(len(inst['fields']))]
        elif op == 'select_i64': result += [[k] for k in ('condition', 'then', 'else')]
        elif op in ('case_i64', 'case_fields_i64'):
            result.append(['scrutinee'])
            for variant in raw['families'][inst['family']]['variants']:
                if op == 'case_i64': result.append(['arms', variant])
                else:
                    arm = inst['arms'][variant]
                    for capture in codes[('thunk', arm['code'])]['captures']:
                        name = capture['name']
                        if arm['captures'][name]['kind'] == 'external':
                            result.append(['arms', variant, 'captures', name, 'value'])
    elif op == 'fill': result = [['hole'], ['value']]
    elif op in ('borrow', 'end_borrow', 'retain', 'drop', 'field', 'force', 'return', 'finish_scalar', 'seal', 'instantiate'):
        result = [['value']]
    return result


def authority(raw_text, observer=None):
    from resource_ir_v8.checker import check_resources
    from resource_ir_v8.metadata import check_metadata
    from resource_ir_v8.packet import emit_packet
    need(type(raw_text) is str and len(raw_text.encode('utf-8')) <= 2097152, 'O_SCHEMA', 'bounded selected raw text')
    raw = json.loads(raw_text)
    recipe = {'raw_utf8': pin(raw_text), 'input': 'fresh json.loads of exact selected raw text'}
    def call(name, fn):
        thunk = lambda: fn(raw)
        return thunk() if observer is None else observer('oracle-lower-api', name, recipe, thunk)
    resource = call('resource_ir_v8.checker.check_resources', check_resources)
    metadata = call('resource_ir_v8.metadata.check_metadata', check_metadata)
    packet = call('resource_ir_v8.packet.emit_packet', emit_packet)
    equal(resource.canonical_json, metadata.canonical_json, 'O_BINDING', 'fresh canonical raw')
    equal(resource.canonical_json, packet.canonical_ir_json, 'O_BINDING', 'fresh packet raw')
    equal(metadata.metadata_json, packet.metadata_json, 'O_BINDING', 'fresh metadata bytes')
    equal((resource.sha256, resource.declaration_sha256, resource.derived_sha256),
          (metadata.ir_sha256, metadata.declaration_sha256, metadata.resource_sha256), 'O_BINDING', 'fresh lower links')
    need(sha(resource.canonical_json) == resource.sha256 and sha(resource.derived_json) == resource.derived_sha256,
         'O_BINDING', 'fresh resource digest')
    need(sha(metadata.metadata_json) == metadata.metadata_sha256, 'O_BINDING', 'fresh metadata digest')
    return raw, resource, metadata, packet


def expected(raw, resource, metadata):
    r, m = json.loads(resource.derived_json), json.loads(metadata.metadata_json)
    codes = {(x['kind'], x['name']): x for x in m['codes']}
    need(len(codes) == len(raw['functions']) + len(raw['codes']), 'O_CODE', 'fresh complete Code census')
    cm, bodies = [], [(None, 'rt8_entry', raw['entry'], dict(root='entry', name=None, segments=[]))]
    for cid, row in enumerate(m['codes']):
        equal(cid, row['id'], 'O_CODE', 'fresh Code ID')
        kind, name = row['kind'], row['name']
        spec = raw['functions' if kind == 'function' else 'codes'][name]
        path = dict(root=kind, name=name, segments=[])
        equal(row['body_path'], path, 'O_PATH', 'fresh body path')
        scope = None if spec['type_scope'] is None else next(x['id'] for x in m['schemes'] if x['name'] == spec['type_scope'])
        equal(row['scope'], scope, 'O_CODE', 'fresh Code scope')
        captures = sorted(spec['captures'])
        equal([x['name'] for x in row['captures']], captures, 'O_CODE', 'capture ordering')
        cm.append(dict(id=cid, kind=kind, name=name, scope=scope, body_path=path,
                       body_sha256=sha(canonical(spec['body'])), symbol='rt8_body_' + str(cid),
                       parameter=spec['parameter'] if kind == 'function' else None, captures=captures))
        bodies.append((cid, 'rt8_body_' + str(cid), spec['body'], path))
    byresource = {pathkey(x['path']): x for x in r['instructions']}
    need(len(byresource) == len(r['instructions']), 'O_PATH', 'fresh resource duplicate path')
    intro_start = {pathkey(x['generalize_path']): x for x in m['introductions']}
    intro_end = {pathkey(x['seal_path']): x for x in m['introductions']}
    use_at = {pathkey(path): u for u in m['uses'] for path in u['occurrences']}
    recs, labels, sites_seen = [], set(), []
    for cid, symbol, body, bp in bodies:
        for path, inst in walk(body, bp['root'], bp['name']):
            key = pathkey(path); fact = byresource[key]; op = inst['op']
            equal(fact['op'], op, 'O_PATH', 'raw/resource opcode')
            roles = roles_for(inst, raw, codes)
            equal([x['role'] for x in fact['inputs']], roles, 'O_OPERAND', 'resource roles')
            names = [operand(inst, role) for role in roles]
            equal([x['role'] for x in fact['outputs']], [['out']] if 'out' in inst else [['hole']] if op == 'fill' else [], 'O_OPERAND', 'resource outputs')
            siteids = fact['sites']; count = len(raw['families'][inst['family']]['variants']) if op == 'case_fields_i64' else int(op in ALLOC)
            equal(len(siteids), count, 'O_SITE', 'Site arm count')
            for arm, sid in enumerate(siteids):
                nonnegative(sid, len(m['sites']) - 1, 'O_SITE'); s = m['sites'][sid]
                equal(s['path'], path, 'O_SITE', 'Site path'); equal(s['arm'], arm if op == 'case_fields_i64' else None, 'O_SITE', 'Site arm')
                if op in ('closure', 'thunk', 'case_fields_i64'):
                    kind = 'function' if op == 'closure' else 'thunk'
                    target = inst['function'] if op == 'closure' else inst['code'] if op == 'thunk' else inst['arms'][raw['families'][inst['family']]['variants'][arm]]['code']
                    equal(s['code'], codes[(kind, target)]['id'], 'O_SITE', 'Site Code association')
                else: equal(s['code'], None, 'O_SITE', 'non-Code Site')
            sites_seen += siteids
            helper = ('rt8_scalar_i64' if inst['kind'] == 'i64' else 'rt8_scalar_bool') if op == 'scalar' else HELPERS[op]
            intro = intro_start.get(key) if op == 'generalize' else intro_end.get(key) if op == 'seal' else None
            use = use_at.get(key) if op == 'instantiate' else None
            need((intro is not None) == (op in ('generalize', 'seal')), 'O_INTRO', 'Intro occurrence')
            need((use is not None) == (op == 'instantiate'), 'O_USE', 'Use occurrence')
            recs.append(dict(path=path, raw=inst, code=cid, symbol=symbol, helper=helper, roles=roles, names=names,
                             fact=fact, sites=siteids, intro=None if intro is None else intro['id'], use=None if use is None else use['id']))
            if op in LABELLED: labels.add(inst['out'])
            if op in ('field', 'force', 'instantiate'): labels.add(inst['value'])
            if op == 'fill': labels.update((inst['hole'], inst['value']))
            if op == 'seal': labels.add(raw_at(raw, intro['generalize_path'])['out'])
            if op == 'case_fields_i64':
                for arm in inst['arms'].values(): labels.update(x['name'] for x in codes[('thunk', arm['code'])]['captures'])
    need(len(recs) == len(byresource), 'O_PATH', 'raw/resource complete inventory')
    equal(sorted(sites_seen), list(range(len(m['sites']))), 'O_SITE', 'all Sites exactly once')
    lr, offset = [], 0
    for lid, value in enumerate(sorted(labels, key=lambda s: s.encode('utf-8'))):
        data = value.encode('utf-8');lr.append(dict(id=lid,offset=offset,utf8_bytes=len(data),value=value,sha256=sha(data)));offset += len(data)+1
    return dict(raw=raw, resource=r, metadata=m, codes=cm, bodies=bodies, records=recs,
                labels=lr, label_bytes=offset, intro_start=intro_start, intro_end=intro_end, use_at=use_at)


DECL = re.compile(r'    (Rt8Handle \*|const (?:Rt8Site|Rt8Code|Rt8Intro|Rt8Instantiation|Rt8Family|Rt8Variant|Rt8Shape|Rt8Env|char) \*|Rt8GenericScope |Rt8CaseArm |Rt8FactoryArm |Rt8FactoryCapture )([hpvg][0-9]+)(?:\[([0-9]+)\])?(?: = \{([0-9]+)\})?;\Z')
VECTOR_TYPES = frozenset(('Rt8Handle *', 'Rt8CaseArm ', 'Rt8FactoryArm ', 'Rt8FactoryCapture '))
EXPR_NAME = re.compile(r'(?:ctx|home|argument|NULL|[hpv][0-9]+|&g[0-9]+|captures\[[0-9]+\]|RT8_(?:PRIM_[A-Z_]+|FACTORY_(?:FIELD|EXTERNAL)))\Z')
LHS = re.compile(r'(?:[hp][0-9]+|v[0-9]+\[[0-9]+\](?:\.[a-z_]+)?)\Z')
BODY_HEAD = re.compile(r'static (void |Rt8Handle \*)(rt8_entry|rt8_body_[0-9]+)\(([^\n]*)\)\n\{\n')
BODY_PARAMETERS = 'Rt8Context *ctx, Rt8Handle *home, Rt8Handle **captures, Rt8Handle *argument, const Rt8Env *env'


def split_args(text):
    out, start, depth = [], 0, 0
    for i, char in enumerate(text):
        if char == '(': depth += 1
        elif char == ')': depth -= 1
        elif char == ',' and depth == 0: out.append(text[start:i].strip());start=i+1
        need(depth >= 0, 'O_SOURCE_BOUNDARY', 'unbalanced expression')
    need(depth == 0, 'O_SOURCE_BOUNDARY', 'unbalanced expression')
    out.append(text[start:].strip())
    return out


def expression(text):
    if re.fullmatch(r'0|[1-9][0-9]*', text): return int(text)
    if EXPR_NAME.fullmatch(text): return text
    m = re.fullmatch(r'INT64_C\(([0-9]+)\)', text)
    if m: return ('i64', int(m[1]))
    m = re.fullmatch(r'\(-INT64_C\(([0-9]+)\)\)', text)
    if m: return ('i64', -int(m[1]))
    if text == '(-INT64_C(9223372036854775807) - INT64_C(1))': return ('i64', -(1 << 63))
    raise OracleError('O_SOURCE_BOUNDARY', 'unsupported/effectful C expression: ' + text[:120])


def parse_body(symbol, text, source_offset):
    declarations, statements, casts = {}, [], []
    declaration_phase = True
    offset = source_offset
    for line in text.splitlines(keepends=True):
        literal = line.rstrip('\n'); decl = DECL.fullmatch(literal)
        if literal.strip() in ('{', '}'):
            raise OracleError('O_LIFETIME', 'nested C lifetime block is not enclosing declaration storage')
        if decl:
            need(declaration_phase, 'O_LIFETIME', 'declaration after body actions')
            ctype,name,count,zero = decl.groups()
            need(name not in declarations, 'O_STORAGE', 'duplicate local declaration')
            count = None if count is None else int(count)
            if name.startswith('g') or ctype == 'Rt8GenericScope ':
                need(name.startswith('g') and ctype == 'Rt8GenericScope ' and
                     count is None and zero == '0', 'O_LIFETIME',
                     'scope token must be an exactly typed zeroed scalar')
            elif name.startswith('v'):
                need(ctype in VECTOR_TYPES and count is not None and count > 0 and zero is None,
                     'O_FRAME', 'vector local must be a positive uninitialized allowed-type array')
            else:
                need(count is None or count > 0, 'O_STORAGE', 'zero-count local array')
                need(zero is None, 'O_SOURCE_BOUNDARY', 'unexpected local initializer')
            declarations[name] = dict(c_type=ctype, count=count, zero=zero, offset=offset, line=line)
        elif literal in ('    (void)home;', '    (void)captures;', '    (void)argument;', '    (void)env;'):
            declaration_phase = False; casts.append(literal)
        elif literal == '    return;':
            declaration_phase = False;statements.append(dict(kind='terminal',offset=offset,line=line))
        else:
            declaration_phase = False
            need(literal.startswith('    ') and literal.endswith(';'), 'O_SOURCE_BOUNDARY', 'unrecognized body statement')
            s = literal[4:-1];target=None;returns=False
            if s.startswith('return '):returns=True;s=s[7:]
            elif ' = ' in s:
                target,s=s.split(' = ',1)
                need(LHS.fullmatch(target), 'O_SOURCE_BOUNDARY', 'unsupported assignment lvalue')
            call=re.fullmatch(r'(rt8_[a-z0-9_]+)\((.*)\)',s)
            if call:
                helper,args=call.groups();args=[expression(x) for x in split_args(args)]
                need(args and args[0]=='ctx', 'O_SOURCE_BOUNDARY', 'helper context')
                statements.append(dict(kind='call',helper=helper,args=args[1:],target=target,returns=returns,offset=offset,line=line))
            else:
                need(target is not None and not returns, 'O_SOURCE_BOUNDARY', 'unsupported non-call statement')
                statements.append(dict(kind='assign',target=target,value=expression(s),offset=offset,line=line))
        offset += len(line.encode('ascii'))
    expected_casts=[] if symbol=='rt8_entry' else ['    (void)home;','    (void)captures;','    (void)argument;','    (void)env;']
    equal(casts,expected_casts,'O_SOURCE_BOUNDARY','fixed unused parameter casts')
    return dict(symbol=symbol,declarations=declarations,statements=statements,text=text,offset=source_offset)


def parse_source(text):
    need(type(text) is str and text.isascii(), 'O_SOURCE_BOUNDARY', 'runtime source must be ASCII numeric templates')
    prefix='#include "ir8_runtime_generated.h"\n#include <stddef.h>\n#include <stdint.h>\n\n'
    need(text.startswith(prefix), 'O_SOURCE_BOUNDARY', 'include allowlist/order')
    need(text.count('static const ')==1,'O_STORAGE','extra program-specific static object')
    marker='static const struct Ir8Runtime_generated_v1 ir8_runtime_generated_root = {\n'
    need(text.count(marker)==1,'O_STORAGE','binding root census')
    rootpos=text.index(marker);first=BODY_HEAD.search(text)
    need(first is not None and first.start()<rootpos,'O_CODE','real entry/body definitions absent')
    pre=text[len(prefix):first.start()];functions=[];cursor=first.start()
    while cursor<rootpos:
        match=BODY_HEAD.match(text,cursor)
        need(match is not None,'O_SOURCE_BOUNDARY','unsupported top-level body declaration')
        ret,symbol,params=match.groups()
        equal((ret,params),('void ','Rt8Context *ctx') if symbol=='rt8_entry' else ('Rt8Handle *',BODY_PARAMETERS),'O_CODE','callback signature')
        end=text.find('\n}\n\n',match.end())
        need(end>=0 and end<rootpos,'O_SOURCE_BOUNDARY','body terminator')
        bodytext=text[match.end():end+1]
        body=parse_body(symbol,bodytext,len(text[:match.end()].encode('ascii')))
        body.update(start=cursor,end=end+4,full=text[cursor:end+4]);functions.append(body);cursor=end+4
    need(cursor==rootpos,'O_SOURCE_BOUNDARY','unparsed body bytes')
    rootend=text.find('\n};\n\n',rootpos)
    need(rootend>=0,'O_STORAGE','root terminator')
    rootend+=5
    return dict(functions=functions,preamble=pre,root=text[rootpos:rootend],root_start=rootpos,root_end=rootend,getters=text[rootend:])


def native_header(codes, labels):
    rows=['#ifndef IR8_RUNTIME_GENERATED_H','#define IR8_RUNTIME_GENERATED_H',
          '#include "rir8_runtime.h"','#include "ir8_packet_generated.h"','',
          'struct Ir8Runtime_generated_v1 {','    Rt8BindingHeader header;']
    if codes: rows.append('    Rt8Code codes['+str(len(codes))+'];')
    if labels:
        rows.append('    uint32_t label_offsets['+str(len(labels))+'];')
        rows.append('    unsigned char label_bytes['+str(sum(x['utf8_bytes']+1 for x in labels))+'];')
    rows += ['};','','Rt8Program ir8_runtime_generated_program(void);',
             'const Ir8PacketExpectedBindings *ir8_runtime_generated_expected_bindings(void);','#endif','']
    return '\n'.join(rows)


def native_preamble(codes, labels):
    rows=['_Static_assert(sizeof(struct Ir8Runtime_generated_v1) <= UINT32_MAX, "binding size");',
          '_Static_assert(_Alignof(struct Ir8Runtime_generated_v1) <= UINT32_MAX, "binding alignment");',
          '_Static_assert(sizeof(struct Ir8Packet_generated_v1) <= UINT32_MAX, "packet size");',
          '_Static_assert(_Alignof(struct Ir8Packet_generated_v1) <= UINT32_MAX, "packet alignment");',
          '_Static_assert(sizeof(struct Ir8Runtime_generated_v1) <= RT8_MAX_STATIC_BYTES && sizeof(struct Ir8Packet_generated_v1) <= RT8_MAX_STATIC_BYTES - sizeof(struct Ir8Runtime_generated_v1), "complete two-root static budget");']
    for name,present in [('codes',bool(codes)),('label_offsets',bool(labels)),('label_bytes',bool(labels))]:
        if present:rows.append('_Static_assert(offsetof(struct Ir8Runtime_generated_v1, '+name+') <= UINT32_MAX, "member offset");')
    return '\n'.join(rows)+'\n\n'


def native_root(codes, labels, bindings):
    def offset(name,present):
        return '(uint32_t)offsetof(struct Ir8Runtime_generated_v1, '+name+')' if present else 'UINT32_MAX'
    pool=b''.join(x['value'].encode('utf-8')+b'\0' for x in labels)
    rows=['static const struct Ir8Runtime_generated_v1 ir8_runtime_generated_root = {','    .header = {',
          '        .magic = {73,82,56,66,73,78,68,0},','        .abi_revision = 1,','        .purpose = 1,',
          '        .binding_bytes = (uint32_t)sizeof(struct Ir8Runtime_generated_v1),',
          '        .binding_alignment = (uint32_t)_Alignof(struct Ir8Runtime_generated_v1),',
          '        .packet_bytes = (uint32_t)sizeof(struct Ir8Packet_generated_v1),',
          '        .packet_alignment = (uint32_t)_Alignof(struct Ir8Packet_generated_v1),',
          '        .code_offset = '+offset('codes',bool(codes))+',','        .code_count = '+str(len(codes))+',',
          '        .label_index_offset = '+offset('label_offsets',bool(labels))+',','        .label_count = '+str(len(labels))+',',
          '        .label_bytes_offset = '+offset('label_bytes',bool(pool))+',','        .label_bytes = '+str(len(pool))+',',
          '        .runtime_total_static_bytes = (uint32_t)(sizeof(struct Ir8Packet_generated_v1) + sizeof(struct Ir8Runtime_generated_v1)),']
    digest_rows=['{ .bytes = {'+','.join(str(x) for x in bytes.fromhex(bindings[k]))+'} }' for k in ('core','raw','declaration','resource','metadata')]
    rows += ['        .expected = { .digests = {'+','.join(digest_rows)+'} },','        .entry = rt8_entry','    }']
    text='\n'.join(rows)
    if codes:
        text+=',\n    .codes = {\n'+',\n'.join('        { .code_id = '+str(c['id'])+', .body = '+c['symbol']+' }' for c in codes)+'\n    }'
    if labels:text+=',\n    .label_offsets = {'+','.join(str(x['offset']) for x in labels)+'}'
    if pool:text+=',\n    .label_bytes = {'+','.join(str(x) for x in pool)+'}'
    return text+'\n};\n\n'


GETTERS='''Rt8Program ir8_runtime_generated_program(void)
{
    Rt8Program program;
    program.packet = ir8_packet_generated_data();
    program.packet_bytes = ir8_packet_generated_size();
    program.binding = &ir8_runtime_generated_root;
    program.binding_bytes = sizeof(ir8_runtime_generated_root);
    return program;
}

const Ir8PacketExpectedBindings *ir8_runtime_generated_expected_bindings(void)
{
    return &ir8_runtime_generated_root.header.expected;
}
'''


def manifest_precheck(e, manifest, expected_, packet):
    x=expected_;m=x['metadata'];recs=x['records']
    keys(manifest,('format','abi_sha256','packet_schema_sha256','bindings','outputs','code_mapping','entry_mapping','instruction_mapping','introduction_mapping','use_mapping','labels','frames','storage_plan','limits','statistics','native_status'))
    equal(manifest['format'],'resource-ir-v8-runtime-emission-manifest/1','O_SCHEMA','manifest format')
    equal(manifest['native_status'],dict(state='emitted-uncompiled-runtime-source',runtime_total_static_bytes=None,callbacks_executed=False,dynamic_guards_executed=False,source_admitted=False),'O_SCHEMA','native status')
    equal(manifest['abi_sha256'],ABI_SHA256,'O_ABI','ABI schema binding')
    equal(manifest['packet_schema_sha256'],PACKET_SCHEMA_SHA256,'O_BINDING','packet schema binding')
    binds=dict(zip(('core','raw','declaration','resource','metadata'),packet.bindings));binds['packet_manifest']=packet.manifest_sha256
    equal(manifest['bindings'],binds,'O_BINDING','fresh bindings')
    equal(manifest['code_mapping'],x['codes'],'O_CODE','complete Code mapping')
    equal(manifest['entry_mapping'],dict(body_path=dict(root='entry',name=None,segments=[]),body_sha256=sha(canonical(x['raw']['entry'])),symbol='rt8_entry'),'O_ENTRY','entry mapping')
    rows=manifest['instruction_mapping'];need(type(rows)is list and len(rows)==len(recs),'O_INSTRUCTION','complete instruction count')
    for actual,record in zip(rows,recs):
        keys(actual,('path','op','code','helper','inputs','output','sites','intro','use'),'O_INSTRUCTION')
        equal(actual['path'],record['path'],'O_PATH','instruction raw path')
        equal(actual['code'],record['code'],'O_PATH','enclosing Code')
        equal(actual['op'],record['raw']['op'],'O_INSTRUCTION','raw opcode')
        need(type(actual['inputs'])is list and len(actual['inputs'])==len(record['roles']),'O_OPERAND','operand count')
        for inp,role,name in zip(actual['inputs'],record['roles'],record['names']):
            keys(inp,('role','raw_name','c_expression'),'O_OPERAND')
            equal(inp['role'],role,'O_OPERAND','operand role');equal(inp['raw_name'],name,'O_OPERAND','operand raw name')
            need(type(inp['c_expression'])is str,'O_OPERAND','operand C expression type')
        if 'out' in record['raw']:
            keys(actual['output'],('raw_name','c_expression'),'O_OPERAND')
            equal(actual['output']['raw_name'],record['raw']['out'],'O_OPERAND','output raw name')
            need(type(actual['output']['c_expression'])is str,'O_OPERAND','output C expression type')
        else:equal(actual['output'],None,'O_OPERAND','non-output instruction, including Fill')
        equal(actual['sites'],record['sites'],'O_SITE','Site/arm correspondence')
        equal(actual['intro'],record['intro'],'O_INTRO','Intro instruction identity')
        equal(actual['use'],record['use'],'O_USE','Use instruction identity')
    intros=manifest['introduction_mapping'];need(type(intros)is list and len(intros)==len(m['introductions']),'O_INTRO','Intro count')
    for a,b in zip(intros,m['introductions']):
        keys(a,('id','scheme','generalize_path','seal_path','result_sites','scope_token','export_expression'),'O_INTRO')
        for k in ('id','scheme','generalize_path','seal_path','result_sites'):equal(a[k],b[k],'O_INTRO','Intro '+k)
    uses=manifest['use_mapping'];need(type(uses)is list and len(uses)==len(m['uses']),'O_USE','Use count')
    for a,b in zip(uses,m['uses']):
        keys(a,('id','name','scheme','arguments','env','result_type','occurrences'),'O_USE')
        for k in ('id','name','scheme','arguments','env','result_type'):equal(a[k],b[k],'O_USE','Use full '+k)
        equal([q['path'] for q in a['occurrences']],b['occurrences'],'O_USE','complete Use occurrences')
        for q in a['occurrences']:keys(q,('path','source_expression','output_expression'),'O_USE')
    for actual,record in zip(rows,recs):equal(actual['helper'],record['helper'],'O_HELPER','type-specific helper')
    equal(manifest['labels'],x['labels'],'O_LABEL','complete unsigned-byte sorted labels')
    return binds


class BodyMachine:
    """Parse pure assignments/accessors; expose the next actual effectful call."""
    def __init__(self, body, labels, abi):
        self.body=body;self.labels=labels;self.abi=abi;self.position=0
        self.values={};self.assigned=set();self.used=set()
        for name,d in body['declarations'].items():
            if d['count'] is not None:
                if d['c_type']=='Rt8Handle *':self.values[name]=[None]*d['count']
                else:self.values[name]=[{} for _ in range(d['count'])]
    def resolve(self,value):
        if type(value)is not str:return value
        if value=='NULL':return None
        if value.startswith('&g'):
            token=value[1:];d=self.body['declarations']
            need(token in d,'O_LIFETIME','undeclared token')
            need(d[token]['c_type']=='Rt8GenericScope ' and d[token]['count'] is None and
                 d[token]['zero']=='0','O_LIFETIME','scope reference requires exactly typed zeroed scalar')
            self.used.add(token);return ('scope',token)
        if re.fullmatch('[pv][0-9]+',value):
            need(value in self.values,'O_OPERAND','use before pure definition');self.used.add(value);return copy.deepcopy(self.values[value])
        return value
    def next(self):
        seq=self.body['statements']
        while self.position<len(seq):
            s=seq[self.position];self.position+=1
            if s['kind']=='terminal':raise OracleError('O_INSTRUCTION','unexpected bare return')
            if s['kind']=='assign':
                target=s['target'];match=re.fullmatch(r'(v[0-9]+)\[([0-9]+)\](?:\.([a-z_]+))?',target)
                need(match is not None,'O_SOURCE_BOUNDARY','only vector pure assignments allowed')
                name,index,field=match.groups();index=int(index)
                need(name in self.values and index<len(self.values[name]),'O_OPERAND','vector target bounds')
                need(target not in self.assigned,'O_OPERAND','vector field assigned twice');self.assigned.add(target)
                value=self.resolve(s['value'])
                if field is None:
                    need(self.body['declarations'][name]['c_type']=='Rt8Handle *','O_OPERAND','vector element type');self.values[name][index]=value
                else:
                    ctype=self.body['declarations'][name]['c_type'].strip()
                    allowed={r['name'] for r in self.abi['ordered_struct_fields'][ctype]}
                    need(field in allowed,'O_OPERAND','vector member domain');self.values[name][index][field]=value
                continue
            helper=s['helper']
            if helper not in ACCESSORS:
                s=dict(s);s['resolved']=[self.resolve(a) for a in s['args']];return s
            target=s['target'];need(target in self.body['declarations'] and target not in self.assigned,'O_OPERAND','accessor target')
            equal(self.body['declarations'][target]['c_type'],ACCESSORS[helper],'O_SOURCE_BOUNDARY','accessor pointer declaration')
            need(not s['returns'] and len(s['args'])==1,'O_SOURCE_BOUNDARY','accessor signature')
            arg=self.resolve(s['args'][0]);self.assigned.add(target)
            if helper=='rt8_label':
                nonnegative(arg,len(self.labels)-1,'O_LABEL');value=('label',self.labels[arg]['value'])
            elif helper=='rt8_site_shape':
                need(type(arg)is tuple and arg[0]=='site','O_SITE','shape from checked Site');value=('shape',arg)
            else:
                nonnegative(arg,4294967294,'O_SITE');value=(helper[4:],arg)
            self.values[target]=value
        return None
    def terminal(self):
        seq=self.body['statements'];need(self.position<len(seq) and seq[self.position]['kind']=='terminal','O_INSTRUCTION','finish helper lacks immediate return');self.position+=1
    def frame(self,code):
        d=self.body['declarations'];h=[n for n in d if n.startswith('h')];p=[n for n in d if n.startswith('p')];g=[n for n in d if n.startswith('g')]
        equal(sorted(h,key=lambda s:int(s[1:])),['h'+str(i) for i in range(len(h))],'O_FRAME','handle local numeric census')
        equal(sorted(p,key=lambda s:int(s[1:])),['p'+str(i) for i in range(len(p))],'O_FRAME','accessor local numeric census')
        equal(sorted(g,key=lambda s:int(s[1:])),['g'+str(i) for i in range(len(g))],'O_FRAME','scope token numeric census')
        for name in h:equal(d[name]['c_type'],'Rt8Handle *','O_FRAME','handle pointer declaration')
        for name in g:
            need(d[name]['c_type']=='Rt8GenericScope ' and d[name]['count'] is None and
                 d[name]['zero']=='0','O_LIFETIME','frame scope declaration shape')
        need(all(n in self.used for n in g),'O_LIFETIME','unused scope token')
        need(all(n in self.assigned for n in p),'O_FRAME','unassigned pointer local')
        need(all(n in self.used for n in p),'O_FRAME','unused metadata/string pointer')
        vector=0
        for n,row in d.items():
            if n.startswith('v'):
                need(row['c_type'] in VECTOR_TYPES and row['count'] is not None and
                     row['count'] > 0 and row['zero'] is None,'O_FRAME','frame vector declaration shape')
            if row['count'] is None:continue
            need(n.startswith('v'),'O_FRAME','non-vector array local')
            ctype=row['c_type'].strip()
            pointers=1 if ctype=='Rt8Handle *' else sum('*' in f['c_type'] or f['c_type'] in ('Rt8Body','Rt8Entry') for f in self.abi['ordered_struct_fields'][ctype])
            vector+=row['count']*pointers
            need(n in self.used,'O_FRAME','unused vector')
        scope_pointers=sum('*' in f['c_type'] for f in self.abi['ordered_struct_fields']['Rt8GenericScope'])
        equal(scope_pointers,4,'O_ABI','GenericScope actual pointer members')
        params=1 if code is None else 5;local=len(h)+scope_pointers*len(g);total=params+local+vector+len(p)
        need(total<=512,'O_FRAME','pointer-cell bound')
        return dict(code=code,symbol=self.body['symbol'],parameter_pointer_cells=params,local_pointer_cells=local,
                    vector_pointer_cells=vector,accessor_pointer_cells=len(p),pointer_cells=total,scope_token_count=len(g),
                    handle_struct_cells=0,storage_strategy='heap-handles-enclosing-pointer-locals')


def verify_calls(x, manifest, parsed, abi):
    frames=[];manifest_instructions=manifest['instruction_mapping'];record_index={pathkey(r['path']):i for i,r in enumerate(x['records'])}
    introductions={};use_expressions={};all_expected_instructions=[]
    families={f['name']:f for f in x['metadata']['families']};flat_variant={};vid=0
    for fam in x['metadata']['families']:
        for v in fam['variants']:flat_variant[(fam['id'],v['index'])]=vid;vid+=1
    def lab(v):return ('label',v)
    def check_arguments(actual,wanted,code='O_OPERAND'):
        equal(actual,wanted,code,'actual helper argument identity/order')
    for bodydesc,body in zip(x['bodies'],parsed['functions']):
        cid,symbol,rawbody,bp=bodydesc;machine=BodyMachine(body,x['labels'],abi);env={};nested=[];targets=set()
        if cid is not None:
            c=x['codes'][cid];env['$home']={'expression':'home','fact':None,'active':True}
            if c['parameter'] is not None:env[c['parameter']]={'expression':'argument','fact':None,'active':True}
            for n,name in enumerate(c['captures']):env[name]={'expression':'captures['+str(n)+']','fact':None,'active':True}
        records=[r for r in x['records'] if r['code']==cid]
        raw_scope_paths={pathkey(r['path']) for r in records if r['raw']['op']=='generalize'}
        token_paths={}
        for record in records:
            inst=record['raw'];op=inst['op'];mapped=manifest_instructions[record_index[pathkey(record['path'])]];values=[]
            for name,fact in zip(record['names'],record['fact']['inputs']):
                need(name in env and env[name]['active'],'O_LIFETIME','raw binding not live');binding=env[name];old=binding['fact']
                if old is not None:
                    fields=('capability','storage','group','mode','anchor','authority_source') if old['kind']=='authority' or fact['kind']=='authority' else tuple(k for k in fact if k!='role')
                    for k in fields:equal(old[k],fact[k],'O_LIFETIME','fresh resource state transition '+k)
                if old is None or (old['kind']=='authority' and fact['kind']!='authority'):binding['fact']=fact
                values.append(binding['expression'])
            equal([q['c_expression'] for q in mapped['inputs']],values,'O_OPERAND','manifest vs independently reconstructed operands')
            call=machine.next();need(call is not None,'O_INSTRUCTION','missing actual helper call')
            equal(call['helper'],record['helper'],'O_HELPER','actual helper selection');args=call['resolved'];target=call['target']
            need(call['returns']==(op=='return'),'O_INSTRUCTION','return helper form')
            if 'out' in inst and op!='generalize' or op=='seal':
                need(type(target)is str and re.fullmatch('h[0-9]+',target) and target in body['declarations'] and target not in targets,'O_OPERAND','single fresh enclosing output local');targets.add(target)
            else:equal(target,None,'O_OPERAND','void/non-output helper assignment')
            all_expected_instructions.append(dict(path=record['path'],helper=record['helper'],inputs=values,output=target))
            if op=='generalize':
                intro=x['metadata']['introductions'][record['intro']]
                need(len(args)==3 and type(args[0])is tuple and args[0][0]=='scope','O_INTRO','scope token argument')
                token=args[0][1];check_arguments(args,[('scope',token),('intro',intro['id']),values[0]],'O_INTRO')
                need(token not in token_paths,'O_LIFETIME','distinct raw generalize occurrences must use distinct body-local tokens')
                token_paths[token]=pathkey(record['path'])
                need(inst['out'] not in env,'O_LIFETIME','generalize rebind');env[inst['out']]={'expression':None,'fact':record['fact']['outputs'][0],'active':False}
                nested.append((env,record,token));env={'$home':{'expression':values[0],'fact':None,'active':True}}
                continue
            if op=='seal':
                need(nested,'O_INTRO','seal without scope');parent,start,token=nested.pop();out=start['raw']['out']
                check_arguments(args,[('scope',token),values[0],lab(out)],'O_INTRO')
                for key in ('capability','storage','node','group','kind','mode','anchor','ticket','ready','provenance','authority_source'):
                    equal(record['fact']['inputs'][0][key],start['fact']['outputs'][0][key],'O_OPERAND','seal transfers same capability '+key)
                equal(x['metadata']['introductions'][record['intro']]['generalize_path'],start['path'],'O_INTRO','matching scope pair')
                env[inst['value']]['active']=False;need(not any(v['active'] for k,v in env.items() if k!='$home'),'O_LIFETIME','live child escapes seal')
                env=parent;env[out]['active']=True;env[out]['expression']=target
                startmap=manifest_instructions[record_index[pathkey(start['path'])]];equal(startmap['output']['c_expression'],target,'O_INTRO','outer export local')
                introductions[record['intro']]=(token,target)
                continue
            if op=='fill':
                old,new=record['fact']['inputs'][0],record['fact']['outputs'][0]
                equal(old['ticket'],True,'O_OPERAND','original Fill ticket');equal(new['ticket'],False,'O_OPERAND','Fill cleared ticket')
                for k in old:
                    if k not in ('role','ticket'):equal(old[k],new[k],'O_OPERAND','Fill same capability '+k)
                env[inst['hole']]['fact']=new
            if op=='instantiate':
                for k in ('capability','storage','node','group','kind','mode','anchor','ticket','ready','provenance','authority_source'):
                    equal(record['fact']['inputs'][0][k],record['fact']['outputs'][0][k],'O_OPERAND','instantiate moves same capability '+k)
            def consume(name):
                need(name!='$home' and name in env and env[name]['active'],'O_LIFETIME','retired binding consumed');env[name]['active']=False
            if op in ('drop','end_borrow','force','return','finish_scalar','instantiate'):consume(inst['value'])
            elif op=='select_i64':consume(inst['then']);consume(inst['else'])
            elif op=='case_i64':
                for v in x['raw']['families'][inst['family']]['variants']:consume(inst['arms'][v])
            if 'out' in inst:
                need(inst['out'] not in env,'O_LIFETIME','raw output rebinding');env[inst['out']]={'expression':target,'fact':record['fact']['outputs'][0],'active':True}
                equal(mapped['output']['c_expression'],target,'O_OPERAND','manifest output vs actual target')
            site=('site',record['sites'][0]) if op in ALLOC else None;shape=('shape',site)
            label=lab(inst['out']) if op in LABELLED else None
            if op in ('new_root','new_below'):
                start=int(op=='new_below');wanted=([values[0]] if start else [])+[len(inst['imports']),values[start:] or None]
            elif op=='alloc':wanted=[values[0],site,shape,values[1:] or None,label]
            elif op in ('closure','thunk'):
                wanted=[values[0],site,('code',x['metadata']['sites'][record['sites'][0]]['code']),values[1:] or None,label]
            elif op=='hole':wanted=[values[0],site,shape,label]
            elif op in ('application','application_borrow'):wanted=[values[0],site,values[1],values[2],label]
            elif op=='fill':wanted=[values[0],values[1],lab(inst['hole']),lab(inst['value'])]
            elif op in ('borrow','end_borrow','retain','drop','return','finish_scalar'):wanted=[values[0]]
            elif op=='force':wanted=[values[0],label,lab(inst['value'])]
            elif op=='field':
                ty=x['resource']['types'][record['fact']['inputs'][0]['type']];fields=sorted(x['raw']['layouts'][ty['atom']]);wanted=[values[0],fields.index(inst['field']),label,lab(inst['value'])]
            elif op=='scalar':wanted=[values[0],site,shape,('i64',inst['value']) if inst['kind']=='i64' else int(inst['value']),label]
            elif op=='prim2':wanted=[values[0],site,PRIMITIVES[inst['primitive']],shape,values[1],values[2],label]
            elif op=='select_i64':wanted=[values[0],values[1],values[2],values[3],label]
            elif op in ('construct_nullary','construct_sum','case_i64','case_fields_i64'):
                family=families[inst['family']];fid=family['id']
                if op in ('construct_nullary','construct_sum'):
                    vi=x['raw']['families'][inst['family']]['variants'].index(inst['variant']);wanted=[values[0],site,('family',fid),('variant',flat_variant[(fid,vi)])]
                    if op=='construct_sum':wanted += [len(inst['fields']),values[1:] or None]
                    wanted.append(label)
                else:
                    arms=[];external=2
                    for arm,variant in enumerate(family['variants']):
                        vref=('variant',flat_variant[(fid,arm)])
                        if op=='case_i64':arms.append(dict(variant=vref,value=values[2+arm]));continue
                        spec=inst['arms'][variant['name']];sid=record['sites'][arm];code=x['metadata']['codes'][x['metadata']['sites'][sid]['code']];captures=[]
                        for cap in code['captures']:
                            binding=spec['captures'][cap['name']];field=binding['kind']=='field'
                            captures.append(dict(name=lab(cap['name']),kind='RT8_FACTORY_FIELD' if field else 'RT8_FACTORY_EXTERNAL',field_index=binding['index'] if field else 0,external=None if field else values[external]))
                            if not field:external+=1
                        arms.append(dict(variant=vref,site=('site',sid),code=('code',code['id']),capture_count=len(captures),captures=captures or None))
                    wanted=[values[0],('family',fid),values[1],len(arms),arms or None,label]
            elif op=='instantiate':
                wanted=[values[0],('instantiation',record['use']),label,lab(inst['value'])];use_expressions[pathkey(record['path'])]=(values[0],target)
            elif op=='finish':wanted=[]
            else:raise OracleError('O_HELPER','unmapped raw operation')
            # Metadata association mismatches are Site failures, while handle/literal
            # mismatches remain operand failures. Compare structure without trusting
            # producer C expressions.
            def association(a,b):
                if type(b)is tuple and b and b[0] in ('site','shape','code','family','variant'):
                    equal(a,b,'O_SITE','actual metadata association');return
                if type(b)is list and type(a)is list and len(a)==len(b):
                    for u,v in zip(a,b):association(u,v)
                elif type(b)is dict and type(a)is dict and a.keys()==b.keys():
                    for k in b:association(a[k],b[k])
            association(args,wanted);check_arguments(args,wanted)
            if op in ('finish','finish_scalar'):machine.terminal()
            if op in ('return','finish','finish_scalar'):
                need(not nested and not any(v['active'] for k,v in env.items() if k!='$home'),'O_LIFETIME','live binding at terminator')
        need(machine.next() is None,'O_INSTRUCTION','extra actual effectful helper')
        need(not nested,'O_INTRO','unclosed scope')
        declared_tokens={n for n in body['declarations'] if n.startswith('g')}
        equal(declared_tokens,set(token_paths),'O_LIFETIME','exact declared/generalize token coverage')
        equal(set(token_paths.values()),raw_scope_paths,'O_LIFETIME','fresh raw generalize path coverage')
        equal(len(token_paths),len(raw_scope_paths),'O_LIFETIME','fresh raw generalize token count')
        frames.append(machine.frame(cid))
        equal(set(n for n in body['declarations'] if n.startswith('h')),targets,'O_FRAME','every handle local exactly one output assignment')
    expected_intros=[]
    for row in x['metadata']['introductions']:
        token,export=introductions[row['id']]
        expected_intros.append(dict(id=row['id'],scheme=row['scheme'],generalize_path=row['generalize_path'],
            seal_path=row['seal_path'],result_sites=row['result_sites'],scope_token=token,export_expression=export))
    expected_uses=[]
    for use in x['metadata']['uses']:
        occurrences=[]
        for path in use['occurrences']:
            source,out=use_expressions[pathkey(path)]
            occurrences.append(dict(path=path,source_expression=source,output_expression=out))
        expected_uses.append(dict(id=use['id'],name=use['name'],scheme=use['scheme'],arguments=use['arguments'],
            env=use['env'],result_type=use['result_type'],occurrences=occurrences))
    equal(manifest['introduction_mapping'],expected_intros,'O_INTRO','full source-derived Intro mapping')
    equal(manifest['use_mapping'],expected_uses,'O_USE','full source-derived Use mapping')
    equal(manifest['frames'],frames,'O_FRAME','complete source-derived frame census')
    equal(len(all_expected_instructions),len(x['records']),'O_INSTRUCTION','complete independent expected call inventory')
    return frames,all_expected_instructions,expected_intros,expected_uses


def _read_abi():
    path=Path(__file__).absolute().parent/'fixtures'/'ir8-runtime-abi-stage05a.json'
    for parent in (path,*path.parents):
        info=parent.lstat()
        need(not stat.S_ISLNK(info.st_mode),'O_ABI','ABI path symlink')
    before=path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size==25780,'O_ABI','ABI bounded regular file')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        opened=os.fstat(fd)
        signature=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        need(signature(opened)==signature(before),'O_ABI','ABI pre-open identity drift')
        blocks=[];remaining=25781
        while remaining:
            part=os.read(fd,min(remaining,65536))
            if not part:break
            blocks.append(part);remaining-=len(part)
        data=b''.join(blocks)
        need(signature(os.fstat(fd))==signature(opened)==signature(path.lstat()),'O_ABI','ABI read identity drift')
    finally:
        os.close(fd)
    need(len(data)==25780 and sha(data)==ABI_SHA256,'O_ABI','exact ABI schema bytes')
    return json.loads(data)


def verify(raw_text, emission, observer=None):
    """Fresh raw authority on EVERY call; accept no producer mapping authority."""
    raw,resource,metadata,packet=authority(raw_text,observer)
    for field in FIELDS:need(hasattr(emission,field),'O_SCHEMA','missing emission field '+field)
    equal(emission.format,'resource-ir-v8-runtime-source/1','O_SCHEMA','emission format')
    equal(emission.canonical_ir_json,resource.canonical_json,'O_BINDING','returned canonical raw bytes')
    equal(emission.metadata_json,metadata.metadata_json,'O_BINDING','returned fresh metadata bytes')
    equal(emission.packet_manifest_json,packet.manifest_json,'O_BINDING','preserved fresh packet manifest')
    equal(emission.packet_header,packet.packet_header,'O_BINDING','preserved lower packet header')
    equal(emission.packet_source,packet.packet_source,'O_BINDING','preserved lower packet source')
    need(type(emission.manifest_json)is str and sha(emission.manifest_json)==emission.manifest_sha256,'O_SCHEMA','manifest hash')
    manifest=json.loads(emission.manifest_json)
    equal(canonical(manifest),emission.manifest_json,'O_SCHEMA','canonical manifest bytes')
    x=expected(raw,resource,metadata);bindings=manifest_precheck(emission,manifest,x,packet)
    keys(manifest['outputs'],OUTPUTS)
    for name in OUTPUTS:equal(manifest['outputs'][name],pin(getattr(emission,name)),'O_SCHEMA','actual output hash/size '+name)
    parsed=parse_source(emission.runtime_source)
    equal([b['symbol'] for b in parsed['functions']],[b[1] for b in x['bodies']],'O_CODE','all actual definitions including dead Code')
    abi=_read_abi()
    frames,instructions,intros,uses=verify_calls(x,manifest,parsed,abi)
    equal(emission.runtime_header,native_header(x['codes'],x['labels']),'O_STORAGE','actual native aggregate member census')
    equal(parsed['preamble'],native_preamble(x['codes'],x['labels']),'O_STORAGE','checked compiler layout expressions')
    equal(parsed['root'],native_root(x['codes'],x['labels'],bindings),'O_STORAGE','actual binding header/rows/bytes')
    equal(parsed['getters'],GETTERS,'O_SOURCE_BOUNDARY','only fixed non-owning getters; no main/execution')
    need(emission.packet_source.count('static const ')==1 and 'ir8_packet_generated_root' in emission.packet_source,
         'O_STORAGE','lower packet program-specific static object census')
    members=[dict(name='header',c_type='Rt8BindingHeader',count=1)]
    if x['codes']:members.append(dict(name='codes',c_type='Rt8Code',count=len(x['codes'])))
    if x['labels']:
        members.extend((dict(name='label_offsets',c_type='uint32_t',count=len(x['labels'])),dict(name='label_bytes',c_type='unsigned char',count=x['label_bytes'])))
    storage=dict(packet=dict(root_type='struct Ir8Packet_generated_v1',root_symbol='ir8_packet_generated_root',bytes=None,alignment=None),
                 binding=dict(root_type='struct Ir8Runtime_generated_v1',root_symbol='ir8_runtime_generated_root',bytes=None,alignment=None,members=members),
                 total_static_bytes=None,total_static_limit=4194304,measurement='sum-complete-aggregate-sizeof',wrapper_storage='by-value-nonowning-not-static')
    equal(manifest['storage_plan'],storage,'O_STORAGE','full storage plan')
    limits=dict(LIMITS);limits['lower_public_calls']=dict(emit_packet=1,check_resources_extra=1)
    equal(manifest['limits'],limits,'O_SCHEMA','fixed limits')
    pre=manifest['statistics'];keys(pre,('phase','creation_units','work_units','source_utf8_bytes','label_utf8_bytes','label_count'))
    equal(pre['phase'],'pre-manifest-serialization','O_SCHEMA','statistics named phase')
    stats=emission.statistics
    need(type(stats)is tuple and len(stats)==8 and all(type(pair)is tuple and len(pair)==2 for pair in stats),'O_SCHEMA','immutable final statistics tuple')
    names=('creation_units','work_units','source_utf8_bytes','manifest_utf8_bytes','label_utf8_bytes','label_count','packet_public_calls','extra_resource_public_calls')
    equal(tuple(k for k,v in stats),names,'O_SCHEMA','ordered statistics keys');final=dict(stats)
    for name,cap in LIMITS.items():
        if name in final:nonnegative(final[name],cap)
    for name in ('creation_units','work_units','source_utf8_bytes','label_utf8_bytes','label_count'):
        nonnegative(pre[name],LIMITS[name]);need(final[name]>=pre[name],'O_SCHEMA','monotonic final counters')
    bytes_expected=sum(len(getattr(emission,n).encode('utf-8')) for n in OUTPUTS)
    equal(pre['source_utf8_bytes'],bytes_expected,'O_SCHEMA','pre source bytes');equal(final['source_utf8_bytes'],bytes_expected,'O_SCHEMA','final source bytes')
    equal(final['manifest_utf8_bytes'],len(emission.manifest_json.encode('utf-8')),'O_SCHEMA','final manifest byte count')
    for obj in (pre,final):
        equal(obj['label_utf8_bytes'],x['label_bytes'],'O_LABEL','label NUL-inclusive byte count');equal(obj['label_count'],len(x['labels']),'O_LABEL','label distinct count')
    equal(final['packet_public_calls'],1,'O_SCHEMA','one packet admission');equal(final['extra_resource_public_calls'],1,'O_SCHEMA','one extra resource admission')
    return dict(resource_derived_json=resource.derived_json,metadata_json=metadata.metadata_json,packet_manifest_json=packet.manifest_json,
                bindings=bindings,lower_reports_typed=dict(resource=typed(resource.report()),metadata=typed(metadata.report()),packet_statistics=typed(packet.statistics)),
                independent_expected=dict(code_mapping=x['codes'],entry_mapping=dict(body_path=dict(root='entry',name=None,segments=[]),
                                          body_sha256=sha(canonical(raw['entry'])),symbol='rt8_entry'),instruction_semantics=instructions,
                                          introduction_mapping=intros,use_mapping=uses,labels=x['labels']),
                independent_source_census=dict(definitions=[b[1] for b in x['bodies']],frames=frames,storage_plan=storage,
                                               program_specific_static_objects=2,getter_program_pointer_cells=2,getter_program_size_t_fields=2,
                                               expected_bindings_getter_locals=0,compiled_layout_measured=False,callbacks_executed=False),
                lower_byte_equivalence_associations=[dict(left='resource.canonical_json',right='metadata.canonical_json',pin=pin(resource.canonical_json)),
                    dict(left='metadata.canonical_json',right='packet.canonical_ir_json',pin=pin(metadata.canonical_json)),
                    dict(left='metadata.metadata_json',right='packet.metadata_json',pin=pin(metadata.metadata_json)),
                    dict(left='fresh packet source/header/manifest',right='emission preserved packet fields',compared='full exact strings')])


def _expr_text(value):
    if type(value)is int:return str(value)
    if type(value)is str:return value
    if type(value)is tuple and value[0]=='i64':
        n=value[1]
        if n==-(1<<63):return '(-INT64_C(9223372036854775807) - INT64_C(1))'
        return 'INT64_C('+str(n)+')' if n>=0 else '(-INT64_C('+str(-n)+'))'
    raise AssertionError('non-template mutation expression')


def _call_line(call):
    prefix='return ' if call['returns'] else (call['target']+' = ') if call['target'] is not None else ''
    return '    '+prefix+call['helper']+'(ctx'+''.join(', '+_expr_text(x) for x in call['args'])+');\n'


class Mutation:
    """Finite edits only; donor manifest helps locate bytes, never accept them."""
    def __init__(self, raw_text, base):
        self.raw=json.loads(raw_text)
        self.base={k:getattr(base,k) for k in FIELDS}
        self.values=dict(self.base)
        self.manifest=json.loads(base.manifest_json)
        self.selectors=[]
    def row(self, op, root=None, name=None, raw_field=None):
        rows=[]
        for i,r in enumerate(self.manifest['instruction_mapping']):
            if r['op']!=op or root is not None and r['path']['root']!=root or name is not None and r['path']['name']!=name:continue
            inst=raw_at(self.raw,r['path'])
            if raw_field is not None and inst.get(raw_field[0])!=raw_field[1]:continue
            rows.append((i,r))
        need(rows,'O_SCHEMA','mutation selector absent: '+op)
        self.selectors.append(dict(op=op,root=root,name=name,raw_field=None if raw_field is None else list(raw_field),
                                   matching_count=len(rows),selected_ordinal=0,selected_path=copy.deepcopy(rows[0][1]['path']),
                                   ordering='entry first then Code ID; generalize pre-order; first matching occurrence'))
        return rows[0]
    def body(self, code):
        symbol='rt8_entry' if code is None else 'rt8_body_'+str(code)
        bodies=[b for b in parse_source(self.values['runtime_source'])['functions'] if b['symbol']==symbol]
        need(len(bodies)==1,'O_SCHEMA','mutation body selector unique');return bodies[0]
    def effect(self,index):
        row=self.manifest['instruction_mapping'][index];body=self.body(row['code'])
        ordinal=sum(r['code']==row['code'] for r in self.manifest['instruction_mapping'][:index])
        effects=[s for s in body['statements'] if s['kind']=='call' and s['helper'] not in ACCESSORS]
        need(ordinal<len(effects),'O_SCHEMA','mutation effect selector range')
        call=effects[ordinal]
        equal(call['helper'],row['helper'],'O_SCHEMA','pristine mutation helper selector')
        return body,call
    def body_replace(self,body,old,new):
        need(body['full'].count(old)==1 and self.values['runtime_source'].count(body['full'])==1,'O_SCHEMA','unique body-local byte selector')
        self.values['runtime_source']=self.values['runtime_source'].replace(body['full'],body['full'].replace(old,new,1),1)
    def change_call(self,index,change):
        body,call=self.effect(index);new=copy.deepcopy(call);change(new)
        self.body_replace(body,call['line'],_call_line(new))
    def change_accessor(self,index,argument_index,new_id,new_helper=None):
        body,call=self.effect(index);target=call['args'][argument_index]
        matches=[s for s in body['statements'] if s['kind']=='call' and s['target']==target and s['helper'] in ACCESSORS]
        need(len(matches)==1,'O_SCHEMA','unique accessor selector');a=matches[0];new=copy.deepcopy(a);new['args']=[new_id]
        if new_helper is not None:new['helper']=new_helper
        self.body_replace(body,a['line'],_call_line(new))
    def native(self):
        parsed=parse_source(self.values['runtime_source']);m=self.manifest
        self.values['runtime_header']=native_header(m['code_mapping'],m['labels'])
        old=self.values['runtime_source'];self.values['runtime_source']=old[:parsed['root_start']]+native_root(m['code_mapping'],m['labels'],m['bindings'])+old[parsed['root_end']:]
        parsed=parse_source(self.values['runtime_source']);prefix='#include "ir8_runtime_generated.h"\n#include <stddef.h>\n#include <stdint.h>\n\n'
        start=len(prefix);end=start+len(parsed['preamble'])
        self.values['runtime_source']=self.values['runtime_source'][:start]+native_preamble(m['code_mapping'],m['labels'])+self.values['runtime_source'][end:]
    def relabel(self,order):
        old=self.manifest['labels'];need(len(set(order))==len(order),'O_SCHEMA','label mutation IDs unique')
        rows=[];offset=0;mapping={oldid:newid for newid,oldid in enumerate(order)}
        for newid,oldid in enumerate(order):
            row=copy.deepcopy(old[oldid]);row['id']=newid;row['offset']=offset;offset+=row['utf8_bytes']+1;rows.append(row)
        def replace(match):
            before=match.group(0);oldid=int(match.group(1))
            return 'rt8_label(ctx, '+str(mapping[oldid])+')' if oldid in mapping else 'NULL'
        self.values['runtime_source']=re.sub(r'rt8_label\(ctx, ([0-9]+)\)',replace,self.values['runtime_source'])
        self.manifest['labels']=rows
        # NULL replacement for an omitted label is still a legal pointer assignment;
        # first failure is the raw-driven label inventory, before body parsing.
        if len(order)!=len(old):
            marker='static const struct Ir8Runtime_generated_v1 ir8_runtime_generated_root = {\n'
            source=self.values['runtime_source'];start=source.index(marker);end=source.index('\n};\n\n',start)+5
            self.values['runtime_header']=native_header(self.manifest['code_mapping'],rows)
            self.values['runtime_source']=source[:start]+native_root(self.manifest['code_mapping'],rows,self.manifest['bindings'])+source[end:]
        else:self.native()
    def finish(self):
        m=self.manifest
        m['outputs']={n:pin(self.values[n]) for n in OUTPUTS}
        source_bytes=sum(v['bytes'] for v in m['outputs'].values())
        m['statistics']['source_utf8_bytes']=source_bytes
        m['statistics']['label_count']=len(m['labels'])
        m['statistics']['label_utf8_bytes']=sum(x['utf8_bytes']+1 for x in m['labels'])
        self.values['manifest_json']=canonical(m);self.values['manifest_sha256']=sha(self.values['manifest_json'])
        stats=dict(self.values['statistics']);stats.update(source_utf8_bytes=source_bytes,manifest_utf8_bytes=len(self.values['manifest_json'].encode('utf-8')),label_count=len(m['labels']),label_utf8_bytes=m['statistics']['label_utf8_bytes'])
        self.values['statistics']=tuple((k,stats[k]) for k,v in self.values['statistics'])
        return SimpleNamespace(**self.values)


def _source_splice(name,old,new):
    old=old.encode('utf-8');new=new.encode('utf-8');left=0
    while left<min(len(old),len(new)) and old[left]==new[left]:left+=1
    tail=0
    while tail<min(len(old)-left,len(new)-left) and old[len(old)-tail-1]==new[len(new)-tail-1]:tail+=1
    right=len(old)-tail;newright=len(new)-tail
    # Include enough predecessor context to make even pure insertion selectors
    # unique. Byte offsets and complete image hashes are retained as well.
    while not old[left:right] or old.count(old[left:right])!=1:
        if left:left-=1
        elif right<len(old):right+=1;newright+=1
        else:raise AssertionError('cannot form unique byte splice')
    removed=old[left:right];inserted=new[left:newright]
    need(old[:left]+inserted+old[right:]==new,'O_SCHEMA','mutation splice reconstruction')
    return dict(artifact=name,byte_offset=left,remove_bytes_base64=base64.b64encode(removed).decode('ascii'),
                insert_bytes_base64=base64.b64encode(inserted).decode('ascii'),exact_match_count=1)


def _json_changes(name,old,new,path=''):
    if type(old)is type(new) and type(old) not in (dict,list,tuple) and old==new:return []
    if type(old)is dict and type(new)is dict and old.keys()==new.keys():
        rows=[]
        for key in old:rows += _json_changes(name,old[key],new[key],path+'/'+key.replace('~','~0').replace('/','~1'))
        return rows
    if type(old)is list and type(new)is list and len(old)==len(new):
        rows=[]
        for i,(a,b) in enumerate(zip(old,new)):rows += _json_changes(name,a,b,path+'/'+str(i))
        return rows
    if type(old)is tuple and type(new)is tuple and typed(old)==typed(new):return []
    return [dict(artifact=name,json_pointer=path,operation='replace',old_typed_value=typed(old),new_typed_value=typed(new),serialization='canonical-json-utf8')]


def _mutation_receipt(case_id,base,mutated):
    before={n:getattr(base,n) for n in FIELDS};after={n:getattr(mutated,n) for n in FIELDS}
    splices=[_source_splice(n,before[n],after[n]) for n in OUTPUTS if before[n]!=after[n]]
    patches=_json_changes('manifest_json',json.loads(before['manifest_json']),json.loads(after['manifest_json']))
    patches += _json_changes('statistics',before['statistics'],after['statistics'])
    patches += _json_changes('manifest_sha256',before['manifest_sha256'],after['manifest_sha256'])
    def image(values,name):
        data=canonical(typed(values[name])) if name=='statistics' else values[name]
        return dict(path=name,**pin(data))
    names=list(OUTPUTS)+['manifest_json','manifest_sha256','statistics']
    return dict(test_id=case_id,base_emission_id=None,expected_diagnostic=None,actual_diagnostic=None,
                source_splices=splices,typed_json_patches=patches,
                pre_images=[image(before,n) for n in names],post_images=[image(after,n) for n in names],
                reconstruction_order=['source_splices in order','manifest_json typed patches in order; canonical JSON encoding',
                                      'statistics typed replacement preserves tuple','manifest_sha256 typed replacement'])


def mutate(case_id, raw_text, base_emission):
    """Exactly44 named non-admitting controls; no public target API calls."""
    need(case_id in {'M%02d'%i for i in range(1,45)},'O_SCHEMA','unknown finite mutation')
    q=Mutation(raw_text,base_emission);m=q.manifest;rows=m['instruction_mapping']
    if case_id=='M01':m['unexpected_private_key']=None
    elif case_id=='M02':
        m['bindings']['metadata']='0'*64 if m['bindings']['metadata']!='0'*64 else '1'*64;q.native()
    elif case_id=='M03':m['abi_sha256']='0'*64
    elif case_id=='M04':
        match=[x for x in m['code_mapping'] if x['name']=='unused_b'];need(len(match)==1,'O_SCHEMA','dead Code selector');code=match[0];cid=code['id']
        need(cid==len(m['code_mapping'])-1,'O_SCHEMA','dead Code must be final fixture ID; no implicit remap')
        body=q.body(cid);q.values['runtime_source']=q.values['runtime_source'].replace(body['full'],'',1)
        m['code_mapping'].pop();m['frames']=[x for x in m['frames'] if x['code']!=cid]
        m['instruction_mapping']=[x for x in rows if x['code']!=cid]
        # Keep labels that actual retained entry/Code source still accesses.
        used=sorted({int(n) for n in re.findall(r'rt8_label\(ctx, ([0-9]+)\)',q.values['runtime_source'])})
        q.relabel(used);q.native()
    elif case_id=='M05':
        need(len(m['code_mapping'])>1,'O_SCHEMA','two Code rows required');m['code_mapping'][1]['id']=m['code_mapping'][0]['id'];q.native()
    elif case_id=='M06':
        code=copy.deepcopy(m['code_mapping'][0]);old=code['id'];newid=len(m['code_mapping']);body=q.body(old)
        clone=body['full'].replace('rt8_body_'+str(old)+'(', 'rt8_body_'+str(newid)+'(',1)
        parsed=parse_source(q.values['runtime_source']);p=parsed['root_start'];q.values['runtime_source']=q.values['runtime_source'][:p]+clone+q.values['runtime_source'][p:]
        code['id']=newid;code['symbol']='rt8_body_'+str(newid);m['code_mapping'].append(code)
        frame=copy.deepcopy(next(f for f in m['frames'] if f['code']==old));frame['code']=newid;frame['symbol']=code['symbol'];m['frames'].append(frame)
        extra=[copy.deepcopy(r) for r in rows if r['code']==old]
        for r in extra:r['code']=newid
        rows.extend(extra);q.native()
    elif case_id=='M07':
        index,row=q.row('scalar',root='entry',raw_field=('value',40));body,call=q.effect(index)
        need(call['line'].count('INT64_C(40)')==1,'O_SCHEMA','literal selector');q.body_replace(body,call['line'],call['line'].replace('INT64_C(40)','INT64_C(41)'))
    elif case_id=='M08':m['entry_mapping']['body_path']['segments']=[0]
    elif case_id=='M09':
        i,r=q.row('generalize',root='function',name='outer');r['path']=dict(root='entry',name=None,segments=list(r['path']['segments']));r['code']=None
    elif case_id in ('M10','M11'):
        i,r=q.row('drop',root='entry');body,call=q.effect(i)
        q.body_replace(body,call['line'],'' if case_id=='M10' else call['line']*2)
        if case_id=='M10':rows.pop(i)
        else:rows.insert(i+1,copy.deepcopy(r))
    elif case_id=='M12':
        i,r=q.row('borrow',root='entry');q.change_call(i,lambda c:c.update(helper='rt8_retain'));r['helper']='rt8_retain'
    elif case_id=='M13':
        i,r=q.row('scalar',root='entry',raw_field=('kind','bool'));q.change_call(i,lambda c:c.update(helper='rt8_scalar_i64'));r['helper']='rt8_scalar_i64'
    elif case_id=='M14':
        i,r=q.row('prim2',root='entry')
        def swap(c):c['args'][4],c['args'][5]=c['args'][5],c['args'][4]
        q.change_call(i,swap);r['inputs'][1]['c_expression'],r['inputs'][2]['c_expression']=r['inputs'][2]['c_expression'],r['inputs'][1]['c_expression']
    elif case_id=='M15':
        i,r=q.row('application',root='entry');body,call=q.effect(i);new=copy.deepcopy(call);new['args'][2]='rt8_retain(ctx, '+call['args'][2]+')';q.body_replace(body,call['line'],_call_line(new))
    elif case_id=='M16':
        i,r=q.row('application');other=next(x['sites'][0] for x in rows if x['op']=='application' and x['sites'][0]!=r['sites'][0]);q.change_accessor(i,1,other);r['sites']=[other]
    elif case_id=='M17':
        i,r=q.row('case_fields_i64');body,call=q.effect(i);vector=call['args'][4]
        need(len(r['sites'])==2 and call['args'][3]==2,'O_SCHEMA','two factory arm selector')
        original=body['full'];changed=original;zero=[]
        for s in body['statements']:
            if s['kind']=='assign' and s['target'].startswith(vector+'[0].'):
                if type(s['value'])is str and re.fullmatch('p[0-9]+',s['value']):zero.append(s['value'])
                changed=changed.replace(s['line'],'',1)
        for name in zero:
            decl=body['declarations'][name];changed=changed.replace(decl['line'],'',1)
            pure=next(s for s in body['statements'] if s['kind']=='call' and s['target']==name)
            changed=changed.replace(pure['line'],'',1)
        decl=body['declarations'][vector];changed=changed.replace(decl['line'],decl['line'].replace('[2]','[1]'),1)
        changed=changed.replace(vector+'[1].',vector+'[0].')
        newcall=copy.deepcopy(call);newcall['args'][3]=1;changed=changed.replace(call['line'],_call_line(newcall),1)
        kept=[n for n in body['declarations'] if n.startswith('p') and n not in zero];renames={n:'p'+str(k) for k,n in enumerate(kept)}
        changed=re.sub(r'\bp[0-9]+\b',lambda mt:renames.get(mt.group(),mt.group()),changed)
        need(q.values['runtime_source'].count(original)==1,'O_SCHEMA','factory body selector');q.values['runtime_source']=q.values['runtime_source'].replace(original,changed,1)
        r['sites']=r['sites'][1:]
        frame=next(f for f in m['frames'] if f['code']==r['code']);frame['vector_pointer_cells']-=4;frame['accessor_pointer_cells']-=len(zero);frame['pointer_cells']-=4+len(zero)
    elif case_id=='M18':
        i,r=q.row('case_fields_i64');body,call=q.effect(i);a,b=r['sites'];text=body['full'];matches=[]
        for s in body['statements']:
            if s['kind']=='call' and s['helper']=='rt8_site' and s['args'][0] in (a,b):
                new=copy.deepcopy(s);new['args']=[b if s['args'][0]==a else a];matches.append((s['line'],_call_line(new)))
        need(len(matches)==2,'O_SCHEMA','factory Site selectors')
        for old,new in matches:need(text.count(old)==1,'O_SCHEMA','unique Site line');text=text.replace(old,new,1)
        q.values['runtime_source']=q.values['runtime_source'].replace(body['full'],text,1);r['sites']=[b,a]
    elif case_id=='M19':
        row=m['introduction_mapping'][0];row['seal_path']=copy.deepcopy(row['seal_path']);need(row['seal_path']['segments'][-1]>0,'O_SCHEMA','non-seal neighbor');row['seal_path']['segments'][-1]-=1
    elif case_id=='M20':
        i,r=q.row('generalize',root='function',name='outer');body=q.body(r['code']);name=r['output']['c_expression'];line=body['declarations'][name]['line'];q.body_replace(body,line,'    {\n'+line+'    }\n')
    elif case_id=='M21':
        i,r=q.row('generalize',root='function',name='outer');body=q.body(r['code']);token=m['introduction_mapping'][r['intro']]['scope_token'];line=body['declarations'][token]['line'];q.body_replace(body,line,line.replace('{0}','{1}'))
    elif case_id=='M22':
        i,r=q.row('instantiate',root='entry');body,call=q.effect(i);h='h'+str(sum(n.startswith('h') for n in body['declarations']))
        new=dict(kind='call',helper='rt8_force',target=h,returns=False,args=[call['args'][0],call['args'][2],call['args'][3]])
        changed=body['full'].replace('{\n','{\n    Rt8Handle *'+h+';\n',1).replace(call['line'],_call_line(new)+call['line'],1)
        q.values['runtime_source']=q.values['runtime_source'].replace(body['full'],changed,1)
        extra=copy.deepcopy(r);extra.update(op='force',helper='rt8_force',use=None,output=dict(raw_name='private_force_result',c_expression=h));rows.insert(i,extra)
        frame=next(f for f in m['frames'] if f['code'] is None);frame['local_pointer_cells']+=1;frame['pointer_cells']+=1
    elif case_id=='M23':
        i,r=q.row('instantiate',root='entry');_,borrow=q.row('borrow',root='entry');expr=borrow['inputs'][0]['c_expression'];q.change_call(i,lambda c:c['args'].__setitem__(0,expr));r['inputs'][0]['c_expression']=expr
    elif case_id=='M24':
        i,r=q.row('application_borrow',root='entry');q.change_call(i,lambda c:c.update(helper='rt8_application'));r['helper']='rt8_application'
    elif case_id=='M25':
        i,r=q.row('fill',root='entry');body,call=q.effect(i);h='h'+str(sum(n.startswith('h') for n in body['declarations']));new=copy.deepcopy(call);new['target']=h
        changed=body['full'].replace('{\n','{\n    Rt8Handle *'+h+';\n',1).replace(call['line'],_call_line(new),1)
        q.values['runtime_source']=q.values['runtime_source'].replace(body['full'],changed,1);r['output']=dict(raw_name=raw_at(q.raw,r['path'])['hole'],c_expression=h)
        frame=next(f for f in m['frames'] if f['code'] is None);frame['local_pointer_cells']+=1;frame['pointer_cells']+=1
    elif case_id=='M26':
        use=m['use_mapping'][0];need(len(use['arguments'])>1,'O_SCHEMA','full dead parameter vector');use['arguments']=use['arguments'][:-1]
    elif case_id=='M27':
        use=next(u for u in m['use_mapping'] if u['occurrences']);use['occurrences']=use['occurrences'][1:]
    elif case_id=='M28':
        body=q.body(None);s=next(s for s in body['statements'] if s['kind']=='call' and s['helper']=='rt8_site')
        q.body_replace(body,s['line'],'    '+s['target']+' = (const Rt8Site *)ir8_packet_generated_data();\n')
    elif case_id=='M29':
        i,r=q.row('scalar',raw_field=('out','literal'));body,call=q.effect(i);shape=call['args'][2]
        s=next(s for s in body['statements'] if s['kind']=='call' and s['target']==shape);new=copy.deepcopy(s);new.update(helper='rt8_shape',args=[0]);q.body_replace(body,s['line'],_call_line(new))
    elif case_id=='M30':
        i,r=q.row('closure',raw_field=('function','constant'));other=next(c['id'] for c in m['code_mapping'] if c['name']=='return_x');q.change_accessor(i,2,other)
    elif case_id=='M31':
        encounter=[]
        for number in re.findall(r'rt8_label\(ctx, ([0-9]+)\)',q.values['runtime_source']):
            number=int(number)
            if number not in encounter:encounter.append(number)
        need(len(encounter)==len(m['labels']) and encounter!=list(range(len(encounter))),'O_SCHEMA','distinct encounter-order control');q.relabel(encounter)
    elif case_id=='M32':
        need(len(m['labels'])>1 and m['labels'][1]['offset']>0,'O_SCHEMA','second offset selector');m['labels'][1]['offset']-=1;q.native()
    elif case_id=='M33':
        body=q.body(None);s=next(s for s in body['statements'] if s['kind']=='call' and s['helper']=='rt8_label');value=m['labels'][s['args'][0]]['value']
        q.body_replace(body,s['line'],'    '+s['target']+' = '+json.dumps(value,ensure_ascii=True)+';\n')
    elif case_id=='M34':
        ids=[r['id'] for r in m['labels'] if r['value']=='fn'];need(len(ids)==1,'O_SCHEMA','FactoryCapture.name fn label');q.relabel([r['id'] for r in m['labels'] if r['id']!=ids[0]])
    elif case_id=='M35':q.values['runtime_source']=q.values['runtime_source'].replace(GETTERS,'static const unsigned char hidden[1] = {0};\n\n'+GETTERS,1)
    elif case_id=='M36':
        need(not m['code_mapping'],'O_SCHEMA','zero-Code donor');q.values['runtime_header']=q.values['runtime_header'].replace('    Rt8BindingHeader header;\n','    Rt8BindingHeader header;\n    Rt8Code codes[0];\n',1)
        m['storage_plan']['binding']['members'].append(dict(name='codes',c_type='Rt8Code',count=0))
    elif case_id=='M37':
        frame=next(f for f in m['frames'] if f['scope_token_count']>0);lost=4*frame['scope_token_count'];frame['local_pointer_cells']-=lost;frame['pointer_cells']-=lost
    elif case_id=='M38':m['native_status']['callbacks_executed']=True
    elif case_id=='M39':q.values['runtime_source']=q.values['runtime_source'].replace('#include <stddef.h>','#include "runtime.h"\n#include <stddef.h>',1)
    elif case_id=='M40':q.values['runtime_source']+='int main(void) { rt8_session_run(); return 0; }\n'
    elif case_id in ('M41','M42','M43'):
        need(sha(raw_text)=='5909f1ddc4317183d7c4f188e8b3e06c927fb313bd212dcd2779883ef4bce7a9',
             'O_SCHEMA','exact P09 scope-control donor')
        body=q.body(None);decl=body['declarations']
        equal({n for n in decl if n.startswith('g')},{'g0','g1'},'O_SCHEMA','two pristine entry tokens')
        selected=[]
        for ordinal,segment in enumerate((1,2)):
            path=dict(root='entry',name=None,segments=[segment])
            seal_path=dict(root='entry',name=None,segments=[segment,'body',1])
            matches=[(i,r) for i,r in enumerate(rows) if r['path']==path and r['op']=='generalize' and r['code'] is None]
            ends=[(i,r) for i,r in enumerate(rows) if r['path']==seal_path and r['op']=='seal' and r['code'] is None]
            need(len(matches)==1 and len(ends)==1,'O_SCHEMA','unique raw begin/seal selector')
            i,r=matches[0];j,end=ends[0];intro_rows=[v for v in m['introduction_mapping'] if v['id']==r['intro']]
            need(len(intro_rows)==1,'O_SCHEMA','unique Intro row');intro=intro_rows[0];token='g'+str(ordinal)
            equal(intro['generalize_path'],path,'O_SCHEMA','pristine Intro begin path')
            equal(intro['seal_path'],seal_path,'O_SCHEMA','pristine Intro seal path')
            equal(intro['scope_token'],token,'O_SCHEMA','pristine numeric token')
            equal(end['intro'],r['intro'],'O_SCHEMA','pristine matched Intro')
            equal(decl[token]['line'],'    Rt8GenericScope '+token+' = {0};\n','O_SCHEMA','exact pristine scope declaration')
            _,begin_call=q.effect(i);_,seal_call=q.effect(j)
            equal(begin_call['args'][0],'&'+token,'O_SCHEMA','pristine begin token')
            equal(seal_call['args'][0],'&'+token,'O_SCHEMA','pristine seal token')
            selected.append((intro,token,begin_call,seal_call))
            q.selectors.append(dict(raw_sha256=sha(raw_text),symbol='rt8_entry',generalize_path=path,
                                    seal_path=seal_path,token=token,matching_begin_count=1,matching_seal_count=1,
                                    ordering='two sequential entry scopes; no nested-control coverage claim'))
        need(selected[0][0]['id']!=selected[1][0]['id'],'O_SCHEMA','distinct pristine Intro IDs')
        equal(sum(r['op']=='generalize' and r['code'] is None for r in rows),2,'O_SCHEMA','exact entry generalize count')
        frame_rows=[f for f in m['frames'] if f['code'] is None]
        need(len(frame_rows)==1,'O_SCHEMA','unique entry frame');frame=frame_rows[0]
        equal(frame['scope_token_count'],2,'O_SCHEMA','pristine two-token frame')
        if case_id=='M41':
            q.body_replace(body,decl['g0']['line'],'    Rt8Handle *g0;\n')
        elif case_id=='M42':
            # Select every predecessor byte before constructing the rejected source.
            # Do not reparse a partially mutated body through the strengthened parser.
            intro,token,begin_call,seal_call=selected[1];changed=body['full']
            edits=[(decl[token]['line'],'')]
            for call in (begin_call,seal_call):
                replacement=copy.deepcopy(call);replacement['args'][0]='&g0'
                edits.append((call['line'],_call_line(replacement)))
            for old,new in edits:
                need(changed.count(old)==1,'O_SCHEMA','unique sequential-alias byte selector');changed=changed.replace(old,new,1)
            q.body_replace(body,body['full'],changed)
            intro['scope_token']='g0';frame['scope_token_count']-=1
            frame['local_pointer_cells']-=4;frame['pointer_cells']-=4
        else:
            need('g2' not in decl,'O_SCHEMA','fresh unused scope token')
            q.body_replace(body,decl['g1']['line'],decl['g1']['line']+'    Rt8GenericScope g2 = {0};\n')
            frame['scope_token_count']+=1;frame['local_pointer_cells']+=4;frame['pointer_cells']+=4
    elif case_id=='M44':
        need(sha(raw_text)=='2dd27c15272a16861f5e406c76dec2b8d0940d0ea1867cdc371923d220c14f95',
             'O_SCHEMA','exact P01 scalar-vector donor')
        body=q.body(None);need(not any(n.startswith('v') for n in body['declarations']),'O_SCHEMA','pristine entry has no vectors')
        prefix='static void rt8_entry(Rt8Context *ctx)\n{\n'
        need(body['full'].startswith(prefix),'O_SCHEMA','exact entry-opening selector')
        q.body_replace(body,prefix,prefix+'    Rt8Handle *v0;\n')
        q.selectors.append(dict(raw_sha256=sha(raw_text),symbol='rt8_entry',token='v0',
                                matching_body_count=1,prior_vector_count=0,unchanged_frame_claims=True))
    mutated=q.finish()
    receipt=_mutation_receipt(case_id,base_emission,mutated)
    receipt['finite_selectors']=q.selectors
    return mutated,receipt
