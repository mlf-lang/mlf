#!/usr/bin/env python3
"""Typed validation for the independent closed/open artifact comparison.
This validates syntax/identity, not the compiler's checked-term proof judgment.
"""
from pathlib import Path
import json
from artifact_binary_reference import Invalid, require

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


def frozen(value):
    return tuple(frozen(x) for x in value) if isinstance(value,(list,tuple)) else value

def validate_type(document, root, family, *, primitive_max=131):
    """Validate the fixed schema with an explicit primitive declaration domain."""
    require(primitive_max in (131, 136), 'supported primitive declaration domain')
    pending, seen = [(root,frozen(family))], set()
    while pending:
        index, typ = pending.pop()
        if (index,typ) in seen: continue
        seen.add((index,typ)); node = document.nodes[index]
        if typ in ('Int','PrimitiveCode'):
            require(node.kind == 0, 'typed integer leaf')
            if typ=='PrimitiveCode': require(0 <= node.data <= primitive_max, 'closed primitive ABI')
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
