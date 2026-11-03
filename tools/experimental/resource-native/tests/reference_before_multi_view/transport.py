"""Strict transport + bounded lowering. This module is NOT an ordinary checker.

A hand-built envelope can test transport/lowering, but is never evidence of a
real CheckedTerm. run_bridge.py owns authentic binary invocation and provenance.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
MAX_BYTES = 1_000_000
MAX_NODES = 10_000
MAX_DEPTH = 100
SCALAR_PRIMITIVES = {
    8: ('addInt', '#i64'), 9: ('subInt', '#i64'),
    10: ('eqInt', '#bool'), 11: ('ltInt', '#bool'), 14: ('mulInt', '#i64'),
}
INT_TYPE = {'tag': 'constructor', 'name': 'Int', 'arguments': []}


def scalar_payload(kind, value):
    if kind == 'int64':
        if type(value) is not int or not -(1 << 63) <= value < (1 << 63):
            raise BridgeError('Int64 payload must be a canonical signed64 integer')
    elif kind == 'bool':
        if type(value) is not bool:
            raise BridgeError('Bool payload must be an actual JSON boolean')
    else:
        raise BridgeError('unknown scalar kind')


def primitive_contract(node):
    code = integer(node['id'], 'primitive.id')
    if code == 13 and node['name'] == 'ifThenElse':
        return ('ifThenElse', '#i64')
    specification = SCALAR_PRIMITIVES.get(code)
    if specification is None or node['name'] != specification[0]:
        raise BridgeError('primitive ID/name is outside the five-primitive scalar contract')
    return specification


def primitive_arguments(node, *, raw=False):
    primitive_contract(node)
    if node['id'] == 13:
        args = node['arguments']
        if type(args) is not list or len(args) != 1:
            raise BridgeError('ifThenElse requires exactly one actual checked type argument')
        validate_type(args[0])
        if not raw and args != [INT_TYPE]:
            raise BridgeError('only concrete intrinsic Int conditional instantiation is admitted')
    elif node['arguments'] != []:
        raise BridgeError('scalar primitives require zero type arguments')


class BridgeError(ValueError):
    pass


def exact(value: Any, keys: set[str], path: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise BridgeError(f"{path}: schema requires exact keys {sorted(keys)}")
    return value


def text(value: Any, path: str) -> str:
    if not isinstance(value, str) or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise BridgeError(f"{path}: expected Unicode scalar string")
    return value


def integer(value: Any, path: str) -> int:
    if type(value) is not int:
        raise BridgeError(f"{path}: expected integer identity")
    return value


def name(value: Any, path: str) -> int:
    exact(value, {"id", "hint"}, path)
    text(value["hint"], path+".hint")
    return integer(value["id"], path+".id")


def strict_pairs(pairs: list) -> dict:
    result = {}
    for k,v in pairs:
        if k in result:
            raise BridgeError("duplicate JSON object key: "+k)
        result[k] = v
    return result


def bounded(value: Any, depth: int = 0, count: list[int] | None = None) -> None:
    if count is None:
        count=[0]
    count[0]+=1
    if count[0] > MAX_NODES or depth > MAX_DEPTH:
        raise BridgeError("transport exceeds bounded node/depth contract")
    if isinstance(value,dict):
        for k,v in value.items():
            text(k,"key"); bounded(v,depth+1,count)
    elif isinstance(value,list):
        for v in value: bounded(v,depth+1,count)
    elif isinstance(value,str):
        text(value,"string")
    elif type(value) not in (int,bool,type(None)):
        raise BridgeError("non-integral transport number")


def validate_kind(value: Any) -> None:
    if not isinstance(value,dict):raise BridgeError("kind must be an object")
    tag=value.get("tag")
    if tag=="star": exact(value,{"tag"},"kind")
    elif tag=="arrow":
        exact(value,{"tag","from","to"},"kind");validate_kind(value["from"]);validate_kind(value["to"])
    else:raise BridgeError("unknown kind")


def validate_type(value: Any) -> None:
    if not isinstance(value,dict):raise BridgeError("type must be an object")
    tag=value.get("tag")
    if tag=="var":exact(value,{"tag","id"},"type");integer(value["id"],"type.id")
    elif tag=="bottom":exact(value,{"tag"},"type")
    elif tag=="bottom_kind":exact(value,{"tag","kind"},"type");validate_kind(value["kind"])
    elif tag=="arrow":
        exact(value,{"tag","from","to"},"type");validate_type(value["from"]);validate_type(value["to"])
    elif tag=="constructor":
        exact(value,{"tag","name","arguments"},"type");text(value["name"],"type.name")
        if not isinstance(value["arguments"],list):raise BridgeError("type arguments must be a list")
        for a in value["arguments"]:validate_type(a)
    elif tag=="apply":
        exact(value,{"tag","function","argument"},"type");validate_type(value["function"]);validate_type(value["argument"])
    elif tag=="forall":
        exact(value,{"tag","id","bound","body"},"type");integer(value["id"],"type.id")
        validate_type(value["bound"]);validate_type(value["body"])
    else:raise BridgeError("unknown type constructor")


def validate_computation(value):
    if type(value) is not dict:raise BridgeError('proof must be an object')
    tag=value.get('tag')
    if tag in ('refl','elim'):exact(value,{'tag'},'proof')
    elif tag=='bottom':
        exact(value,{'tag','type'},'proof');validate_type(value['type'])
    elif tag in ('hyp','intro'):
        exact(value,{'tag','id'},'proof');integer(value['id'],'proof.id')
    elif tag=='intro_kind':
        exact(value,{'tag','id','kind'},'proof');integer(value['id'],'proof.id');validate_kind(value['kind'])
    elif tag=='inner':
        exact(value,{'tag','witness'},'proof');validate_computation(value['witness'])
    elif tag=='outer':
        exact(value,{'tag','id','witness'},'proof');integer(value['id'],'proof.id');validate_computation(value['witness'])
    elif tag=='then':
        exact(value,{'tag','first','second'},'proof');validate_computation(value['first']);validate_computation(value['second'])
    else:raise BridgeError('unknown proof constructor')


def validate_field(value):
    if type(value) is not dict:raise BridgeError('raw declaration field must be object')
    tag=value.get('tag')
    if tag=='parameter':exact(value,{'tag','name'},'field');text(value['name'],'field.name')
    elif tag=='function':
        exact(value,{'tag','from','to'},'field');validate_field(value['from']);validate_field(value['to'])
    elif tag=='applied':
        exact(value,{'tag','name','arguments'},'field');text(value['name'],'field.name')
        if type(value['arguments']) is not list:raise BridgeError('field arguments must be array')
        for item in value['arguments']:validate_field(item)
    elif tag=='application':
        exact(value,{'tag','function','argument'},'field');validate_field(value['function']);validate_field(value['argument'])
    elif tag=='quantified':
        exact(value,{'tag','name','kind','body'},'field');text(value['name'],'field.name');validate_kind(value['kind']);validate_field(value['body'])
    else:raise BridgeError('unknown raw declaration field')


def validate_declarations(values):
    if type(values) is not list:raise BridgeError('raw declarations must be array')
    for d in values:
        exact(d,{'tag','name','parameters','constructors'},'raw declaration')
        text(d['name'],'declaration.name')
        if d['tag'] not in ('data','data_kind'):raise BridgeError('unknown declaration kind')
        if type(d['parameters']) is not list or type(d['constructors']) is not list:raise BridgeError('declaration arrays required')
        for p in d['parameters']:
            if d['tag']=='data':text(p,'declaration.parameter')
            else:
                exact(p,{'name','kind'},'declaration.parameter');text(p['name'],'parameter.name');validate_kind(p['kind'])
        for c in d['constructors']:
            exact(c,{'name','fields'},'declaration.constructor');text(c['name'],'constructor.name')
            if type(c['fields']) is not list:raise BridgeError('constructor fields must be array')
            for f in c['fields']:validate_field(f)


def contains_conditional(node):
    if type(node) is dict:
        return (node.get('tag')=='primitive' and node.get('id')==13) or any(contains_conditional(x) for x in node.values())
    return type(node) is list and any(contains_conditional(x) for x in node)


def substitute_closed_int_type(value,binder):
    """Exact closed-Int specialization of original T.substitute, not inference."""
    tag=value['tag']
    if tag=='var':return INT_TYPE if value['id']==binder else value
    if tag in ('bottom','bottom_kind'):return value
    if tag=='arrow':return value|{'from':substitute_closed_int_type(value['from'],binder),'to':substitute_closed_int_type(value['to'],binder)}
    if tag=='constructor':return value|{'arguments':[substitute_closed_int_type(t,binder) for t in value['arguments']]}
    if tag=='apply':
        f=substitute_closed_int_type(value['function'],binder);a=substitute_closed_int_type(value['argument'],binder)
        # Bootstrap.X.Type.substitute uses T.apply, which folds constructor application.
        return f|{'arguments':f['arguments']+[a]} if f['tag']=='constructor' else value|{'function':f,'argument':a}
    if tag=='forall':
        return value|{'bound':substitute_closed_int_type(value['bound'],binder),
                     'body':value['body'] if value['id']==binder else substitute_closed_int_type(value['body'],binder)}
    raise BridgeError('unsupported type substitution shape')


def standard_argument(witness):
    if (witness.get('tag')=='then' and witness['first'].get('tag')=='inner'
        and witness['first']['witness'].get('tag')=='bottom' and witness['second']=={'tag':'elim'}):
        return witness['first']['witness']['type']
    raise BridgeError('proof is not an exact standard type instantiation')


def substitute_closed_int_proof(witness,binder):
    if witness=={'tag':'refl'}:return witness
    argument=standard_argument(witness)
    return {'tag':'then','first':{'tag':'inner','witness':{'tag':'bottom','type':substitute_closed_int_type(argument,binder)}},'second':{'tag':'elim'}}


def substitute_closed_int_term(node,binder):
    tag=node['tag'];sub=lambda n:substitute_closed_int_term(n,binder);ty=lambda t:substitute_closed_int_type(t,binder)
    if tag in ('unit','var','int64','bool'):return node
    if tag in ('primitive','constructor'):return node|{'arguments':[ty(t) for t in node['arguments']]}
    if tag=='lambda':return node|{'parameter_type':ty(node['parameter_type']),'body':sub(node['body'])}
    if tag=='application':return node|{'function':sub(node['function']),'argument':sub(node['argument'])}
    if tag=='let':return node|{'value':sub(node['value']),'body':sub(node['body'])}
    if tag=='letrec':return node|{'bindings':[b|{'type':ty(b['type']),'value':sub(b['value'])} for b in node['bindings']],'body':sub(node['body'])}
    if tag=='case':return node|{'scrutinee':sub(node['scrutinee']),'result_type':ty(node['result_type']),
                               'alternatives':[a|{'body':sub(a['body'])} for a in node['alternatives']]}
    if tag=='with_data':return node|{'body':sub(node['body'])}
    if tag=='type_lambda':
        # A binder does not scope over its own bound. Closed Int cannot be captured.
        return node|{'bound':ty(node['bound']),'body':node['body'] if node['id']==binder else sub(node['body'])}
    if tag=='type_application':return node|{'value':sub(node['value']),'witness':substitute_closed_int_proof(node['witness'],binder)}
    raise BridgeError('unsupported raw term substitution shape')


def normalize_conditional_raw(node):
    """Replay only the recorded bounded transformation; not ordinary checking."""
    steps=[]
    def visit(n):
        tag=n['tag']
        if tag=='type_application':
            proof=n['witness']
            if proof=={'tag':'refl'}:
                steps.append({'rule':'erase_refl','witness':proof});return visit(n['value'])
            argument=standard_argument(proof);value=n['value']
            if argument!=INT_TYPE or value['tag']!='type_lambda':raise BridgeError('unsupported/non-Int instantiation redex')
            if value['bound'] not in ({'tag':'bottom'},{'tag':'bottom_kind','kind':{'tag':'star'}}):
                raise BridgeError('closed Int instantiation requires bottom Star bound')
            steps.append({'rule':'instantiate_closed_int','binder':value['id'],'bound':value['bound'],'argument':argument,'witness':proof})
            return visit(substitute_closed_int_term(value['body'],value['id']))
        if tag=='primitive':primitive_arguments(n);return n
        if tag in ('unit','var','int64','bool','constructor'):return n
        if tag in ('lambda','type_lambda','with_data'):return n|{'body':visit(n['body'])}
        if tag=='application':return n|{'function':visit(n['function']),'argument':visit(n['argument'])}
        if tag=='let':return n|{'value':visit(n['value']),'body':visit(n['body'])}
        if tag=='letrec':return n|{'bindings':[b|{'value':visit(b['value'])} for b in n['bindings']],'body':visit(n['body'])}
        if tag=='case':return n|{'scrutinee':visit(n['scrutinee']),'alternatives':[a|{'body':visit(a['body'])} for a in n['alternatives']]}
        raise BridgeError('unsupported normalization node')
    result=visit(node)
    return result,steps


def strip_data_evidence(value):
    if type(value) is dict:
        if value.get('tag')=='with_data':return strip_data_evidence(value['body'])
        return {k:strip_data_evidence(v) for k,v in value.items()}
    if type(value) is list:return [strip_data_evidence(v) for v in value]
    return value


def alpha_type_equal(a,b,left=None,right=None,depth=0):
    # Mirrors only type equality; this is not proof checking or term inference.
    left={} if left is None else left;right={} if right is None else right
    def norm(t):
        if t=={'tag':'bottom_kind','kind':{'tag':'star'}}:return {'tag':'bottom'}
        if t['tag']=='apply':
            f=norm(t['function']);x=norm(t['argument'])
            if f['tag']=='constructor':return f|{'arguments':f['arguments']+[x]}
            return t|{'function':f,'argument':x}
        return t
    a=norm(a);b=norm(b)
    if a['tag']!=b['tag']:return False
    eq=lambda x,y:alpha_type_equal(x,y,left,right,depth)
    tag=a['tag']
    if tag=='var':
        return (('bound',left[a['id']]) if a['id'] in left else ('free',a['id'])) == (('bound',right[b['id']]) if b['id'] in right else ('free',b['id']))
    if tag in ('bottom','bottom_kind'):return a==b
    if tag=='arrow':return eq(a['from'],b['from']) and eq(a['to'],b['to'])
    if tag=='constructor':return a['name']==b['name'] and len(a['arguments'])==len(b['arguments']) and all(eq(x,y) for x,y in zip(a['arguments'],b['arguments']))
    if tag=='apply':return eq(a['function'],b['function']) and eq(a['argument'],b['argument'])
    if tag=='forall':return eq(a['bound'],b['bound']) and alpha_type_equal(a['body'],b['body'],left|{a['id']:depth},right|{b['id']:depth},depth+1)
    return False


def validate_inventory(inventory):
    if type(inventory) is not dict:raise BridgeError('bad declaration inventory')
    if inventory.get('status')=='available':
        exact(inventory,{'status','bindings'},'bindings')
        if type(inventory['bindings']) is not list:raise BridgeError('bad binding list')
        for b in inventory['bindings']:
            exact(b,{'name','type'},'binding');name(b['name'],'binding.name');validate_type(b['type'])
    elif inventory.get('status')=='unavailable':
        exact(inventory,{'status','diagnostic'},'bindings');text(inventory['diagnostic'],'bindings.diagnostic')
    else:raise BridgeError('unknown declaration inventory status')


# Captured implementation fragment inserted into transport.py; no runtime import.
BOOL_TYPE={'tag':'constructor','name':'Bool','arguments':[]}

def closed_scalar_argument(t):
    return t==INT_TYPE or t==BOOL_TYPE

def substitute_closed_type(t,binder,argument):
    tag=t['tag'];sub=lambda x:substitute_closed_type(x,binder,argument)
    if tag=='var':return argument if t['id']==binder else t
    if tag in ('bottom','bottom_kind'):return t
    if tag=='arrow':return t|{'from':sub(t['from']),'to':sub(t['to'])}
    if tag=='constructor':return t|{'arguments':[sub(x)for x in t['arguments']]}
    if tag=='apply':
        f=sub(t['function']);a=sub(t['argument'])
        return f|{'arguments':f['arguments']+[a]} if f['tag']=='constructor' else t|{'function':f,'argument':a}
    if tag=='forall':return t|{'bound':sub(t['bound']),'body':t['body']if t['id']==binder else sub(t['body'])}
    raise BridgeError('unsupported closed type substitution')

def substitute_closed_proof(p,binder,argument):
    tag=p['tag'];sub=lambda x:substitute_closed_proof(x,binder,argument)
    if tag in ('refl','elim'):return p
    if tag=='bottom':return p|{'type':substitute_closed_type(p['type'],binder,argument)}
    if tag=='inner':return p|{'witness':sub(p['witness'])}
    if tag=='then':return p|{'first':sub(p['first']),'second':sub(p['second'])}
    raise BridgeError('unsupported proof in closed substitution')

def substitute_closed_term(n,binder,argument):
    tag=n['tag'];sub=lambda x:substitute_closed_term(x,binder,argument);ty=lambda x:substitute_closed_type(x,binder,argument)
    if tag in ('unit','var','int64','bool'):return n
    if tag in ('primitive','constructor'):return n|{'arguments':[ty(x)for x in n['arguments']]}
    if tag=='lambda':return n|{'parameter_type':ty(n['parameter_type']),'body':sub(n['body'])}
    if tag=='application':return n|{'function':sub(n['function']),'argument':sub(n['argument'])}
    if tag=='let':return n|{'value':sub(n['value']),'body':sub(n['body'])}
    if tag=='letrec':return n|{'bindings':[b|{'type':ty(b['type']),'value':sub(b['value'])}for b in n['bindings']],'body':sub(n['body'])}
    if tag=='case':return n|{'scrutinee':sub(n['scrutinee']),'result_type':ty(n['result_type']),'alternatives':[a|{'body':sub(a['body'])}for a in n['alternatives']]}
    if tag=='with_data':return n|{'body':sub(n['body'])}
    if tag=='type_lambda':return n|{'bound':ty(n['bound']),'body':n['body']if n['id']==binder else sub(n['body'])}
    if tag=='type_application':return n|{'value':sub(n['value']),'witness':substitute_closed_proof(n['witness'],binder,argument)}
    raise BridgeError('unsupported closed term substitution')

def term_skeleton(n):
    tag=n['tag'];sk=term_skeleton
    if tag=='type_lambda':return sk(n['body'])
    if tag=='type_application':return sk(n['value'])
    if tag=='with_data':return n|{'body':sk(n['body'])}
    if tag in ('unit','var','int64','bool'):return n
    if tag in ('primitive','constructor'):return {k:v for k,v in n.items()if k!='arguments'}
    if tag=='lambda':return {'tag':tag,'parameter':n['parameter'],'body':sk(n['body'])}
    if tag=='application':return n|{'function':sk(n['function']),'argument':sk(n['argument'])}
    if tag=='let':return n|{'value':sk(n['value']),'body':sk(n['body'])}
    if tag=='letrec':return n|{'bindings':[{'name':b['name'],'value':sk(b['value'])}for b in n['bindings']],'body':sk(n['body'])}
    if tag=='case':return {'tag':tag,'scrutinee':sk(n['scrutinee']),'alternatives':[a|{'body':sk(a['body'])}for a in n['alternatives']]}
    raise BridgeError('unsupported term skeleton node')

def closed_proof_actions(proof):
    """Preserve original trees; flatten only composition/identity for interpretation."""
    atoms=[]
    def flatten(p):
        if p['tag']=='then':flatten(p['first']);flatten(p['second'])
        else:atoms.append(p)
    flatten(proof)
    if len(atoms)>64:raise BridgeError('closed proof atom budget exceeded')
    pending=None;actions=[]
    for p in atoms:
        if p=={'tag':'refl'}:actions.append(('refl',None,proof));continue
        if p['tag']=='inner' and p['witness']['tag']=='bottom' and pending is None:
            pending=p['witness']['type'];continue
        if p=={'tag':'elim'} and pending is not None:
            actions.append(('instantiate',pending,proof));pending=None;continue
        raise BridgeError('closed proof is not exact standard elimination pairs')
    if pending is not None:raise BridgeError('incomplete standard elimination pair')
    return actions

def closed_type_spine(n):
    proofs=[]
    while n['tag']=='type_application':proofs.append(n['witness']);n=n['value']
    proofs.reverse();return n,proofs

def type_prefix(n):
    result=[]
    while n['tag']=='type_lambda':
        result.append({'id':n['id'],'bound':n['bound']});n=n['body']
    return result,n

def bottom_star_type(t):return t in ({'tag':'bottom'},{'tag':'bottom_kind','kind':{'tag':'star'}})

def raw_field_type(f,parameters):
    tag=f['tag']
    if tag=='parameter':
        if f['name']not in parameters:raise BridgeError('unknown declared field parameter')
        return parameters[f['name']]
    if tag=='applied':return {'tag':'constructor','name':f['name'],'arguments':[raw_field_type(x,parameters)for x in f['arguments']]}
    if tag=='function':return {'tag':'arrow','from':raw_field_type(f['from'],parameters),'to':raw_field_type(f['to'],parameters)}
    raise BridgeError('unsupported generic field for raw replay inference')

def raw_constructor_type(name_,args,declarations):
    for d in declarations:
        for c in d['constructors']:
            if c['name']==name_:
                parameters=[x if d['tag']=='data' else x['name']for x in d['parameters']]
                if len(parameters)!=len(args):raise BridgeError('raw constructor type arity differs')
                result={'tag':'constructor','name':d['name'],'arguments':args}
                for f in reversed(c['fields']):result={'tag':'arrow','from':raw_field_type(f,dict(zip(parameters,args))),'to':result}
                return result
    if name_=='()' and args==[]:return {'tag':'constructor','name':'()','arguments':[]}
    raise BridgeError('raw inference constructor lacks exact declaration')

def raw_compute_type(p,source):
    tag=p['tag']
    if tag=='refl':return source
    if tag=='then':return raw_compute_type(p['second'],raw_compute_type(p['first'],source))
    if tag=='bottom':
        if not bottom_star_type(source):raise BridgeError('bottom proof has nonbottom-Star source')
        return p['type']
    if tag=='inner':
        if source['tag']!='forall':raise BridgeError('inner proof lacks forall source')
        return source|{'bound':raw_compute_type(p['witness'],source['bound'])}
    if tag=='elim':
        if source['tag']!='forall':raise BridgeError('elim proof lacks forall source')
        return substitute_closed_type(source['body'],source['id'],source['bound'])
    raise BridgeError('unknown raw proof inference')

def raw_infer_type(n,env=None,declarations=None):
    """Replay a typed AST schema, NOT a substitute for actual ordinary K.check."""
    env={}if env is None else env;ds=[]if declarations is None else declarations;tag=n['tag']
    infer=lambda x,scope=env:raw_infer_type(x,scope,ds)
    if tag=='unit':return {'tag':'constructor','name':'()','arguments':[]}
    if tag=='int64':return INT_TYPE
    if tag=='bool':return BOOL_TYPE
    if tag=='var':
        if n['name']['id']not in env:raise BridgeError('raw inference free variable')
        return env[n['name']['id']]
    if tag=='with_data':return raw_infer_type(n['body'],env,n['declarations'])
    if tag=='type_lambda':return {'tag':'forall','id':n['id'],'bound':n['bound'],'body':infer(n['body'])}
    if tag=='type_application':return raw_compute_type(n['witness'],infer(n['value']))
    if tag=='lambda':return {'tag':'arrow','from':n['parameter_type'],'to':infer(n['body'],env|{n['parameter']['id']:n['parameter_type']})}
    if tag=='application':
        f=infer(n['function']);a=infer(n['argument'])
        if f['tag']!='arrow' or not alpha_type_equal(f['from'],a):raise BridgeError('raw inference application mismatch')
        return f['to']
    if tag=='let':return infer(n['body'],env|{n['name']['id']:infer(n['value'])})
    if tag=='letrec':
        scope=env|{b['name']['id']:b['type']for b in n['bindings']}
        for b in n['bindings']:
            if not alpha_type_equal(infer(b['value'],scope),b['type']):raise BridgeError('raw recursive annotation mismatch')
        return infer(n['body'],scope)
    if tag=='constructor':return raw_constructor_type(n['name'],n['arguments'],ds)
    if tag=='primitive':
        primitive_arguments(n,raw=True)
        if n['id']==13:
            a=n['arguments'][0];return {'tag':'arrow','from':BOOL_TYPE,'to':{'tag':'arrow','from':a,'to':{'tag':'arrow','from':a,'to':a}}}
        result=BOOL_TYPE if n['id']in(10,11)else INT_TYPE
        return {'tag':'arrow','from':INT_TYPE,'to':{'tag':'arrow','from':INT_TYPE,'to':result}}
    if tag=='case':
        subject=infer(n['scrutinee']);result=n['result_type']
        if subject['tag']!='constructor':raise BridgeError('raw case lacks concrete nominal constructor type')
        for a in n['alternatives']:
            typ=raw_constructor_type(a['pattern']['constructor'],subject['arguments'],ds);fields=[]
            while typ['tag']=='arrow':fields.append(typ['from']);typ=typ['to']
            if not alpha_type_equal(typ,subject)or len(fields)!=len(a['pattern']['fields']):raise BridgeError('raw case family/arity mismatch')
            scope=env|{name_['id']:field for name_,field in zip(a['pattern']['fields'],fields)if name_ is not None}
            if not alpha_type_equal(infer(a['body'],scope),result):raise BridgeError('raw branch result mismatch')
        return result
    raise BridgeError('unsupported raw inference node')

def closed_occurrences(body,binding,prefix,path):
    uses=[];arguments=None;target=binding['id']
    def visit(n,p):
        nonlocal arguments
        tag=n['tag'];base,proofs=closed_type_spine(n)
        if base['tag']=='var' and base['name']['id']==target:
            if not proofs:raise BridgeError('bare or escaping polymorphic use')
            actions=[a for proof in proofs for a in closed_proof_actions(proof)];args=[a for op,a,_ in actions if op=='instantiate']
            if len(args)!=len(prefix)or not all(closed_scalar_argument(a)for a in args):raise BridgeError('open/partial polymorphic occurrence')
            if arguments is not None and args!=arguments:raise BridgeError('mixed closed instantiations of term binder')
            arguments=args;uses.append({'path':p,'witnesses':proofs})
            if len(uses)>256:raise BridgeError('polymorphic occurrence bound exceeded')
            return base
        if tag in ('unit','var','int64','bool','constructor','primitive'):return n
        if tag=='type_application':return n|{'value':visit(n['value'],p)}
        if tag=='type_lambda':return n|{'body':visit(n['body'],p)}
        if tag=='with_data':return n|{'body':visit(n['body'],p+['body'])}
        if tag=='lambda':return n if n['parameter']['id']==target else n|{'body':visit(n['body'],p+['body'])}
        if tag=='application':return n|{'function':visit(n['function'],p+['function']),'argument':visit(n['argument'],p+['argument'])}
        if tag=='let':return n|{'value':visit(n['value'],p+['value']),'body':n['body']if n['name']['id']==target else visit(n['body'],p+['body'])}
        if tag=='letrec':
            if target in {b['name']['id']for b in n['bindings']}:return n
            return n|{'bindings':[b|{'value':visit(b['value'],p+['bindings',str(i),'value'])}for i,b in enumerate(n['bindings'])],'body':visit(n['body'],p+['body'])}
        if tag=='case':return n|{'scrutinee':visit(n['scrutinee'],p+['scrutinee']),'alternatives':[a if target in {x['id']for x in a['pattern']['fields']if x is not None}else a|{'body':visit(a['body'],p+['alternatives',str(i),'body'])}for i,a in enumerate(n['alternatives'])]}
        raise BridgeError('unknown occurrence syntax')
    result=visit(body,path)
    if not uses:raise BridgeError('unused unresolved generalized binding')
    return result,arguments,uses

def normalize_closed_instances_raw(node):
    steps=[];bindings=0
    def direct(n):
        tag=n['tag']
        if tag=='type_application':
            base,proofs=closed_type_spine(n);actions=[a for proof in proofs for a in closed_proof_actions(proof)]
            args=[a for op,a,_ in actions if op=='instantiate'];prefix,_=type_prefix(base)
            if not args:
                for op,a,proof in actions:steps.append({'rule':'erase_refl','witness':{'tag':'refl'}})
                return direct(base)
            if prefix:
                if len(prefix)!=len(args)or len(prefix)>8 or len({x['id']for x in prefix})!=len(prefix)or not all(bottom_star_type(x['bound'])for x in prefix):raise BridgeError('direct prefix arity/identity/bound mismatch')
            if prefix and all(closed_scalar_argument(a)for a in args):
                current=base
                for op,a,proof in actions:
                    if op=='refl':steps.append({'rule':'erase_refl','witness':{'tag':'refl'}});continue
                    if not bottom_star_type(current['bound']):raise BridgeError('direct bound must be bottom Star')
                    steps.append({'rule':'instantiate_closed','binder':current['id'],'bound':current['bound'],'argument':a,'witness':proof})
                    current=substitute_closed_term(current['body'],current['id'],a)
                return direct(current)
            current=direct(base)
            for proof in proofs:current={'tag':'type_application','value':current,'witness':proof}
            return current
        if tag in ('unit','var','int64','bool','constructor','primitive'):return n
        if tag in ('lambda','type_lambda','with_data'):return n|{'body':direct(n['body'])}
        if tag=='application':return n|{'function':direct(n['function']),'argument':direct(n['argument'])}
        if tag=='let':return n|{'value':direct(n['value']),'body':direct(n['body'])}
        if tag=='letrec':return n|{'bindings':[b|{'value':direct(b['value'])}for b in n['bindings']],'body':direct(n['body'])}
        if tag=='case':return n|{'scrutinee':direct(n['scrutinee']),'alternatives':[a|{'body':direct(a['body'])}for a in n['alternatives']]}
        raise BridgeError('unsupported direct traversal')
    def specialize(n,env,ds,path):
        nonlocal bindings
        tag=n['tag'];inf=lambda x,scope=env:raw_infer_type(x,scope,ds)
        if tag=='let':
            prefix,_=type_prefix(n['value'])
            if prefix:
                if len(prefix)>8 or len({x['id']for x in prefix})!=len(prefix)or not all(bottom_star_type(x['bound'])for x in prefix):raise BridgeError('unsupported generalized-let prefix')
                body,args,uses=closed_occurrences(n['body'],n['name'],prefix,path+['body'])
                original=inf(n['value']);result=original;rhs=n['value']
                for a in args:
                    if result['tag']!='forall' or rhs['tag']!='type_lambda':raise BridgeError('binding scheme/prefix differs')
                    result=substitute_closed_type(result['body'],result['id'],a);rhs=substitute_closed_term(rhs['body'],rhs['id'],a)
                steps.append({'rule':'specialize_let','binding':n['name'],'type_binders':prefix,'arguments':args,
                              'original_type':original,'instantiated_type':result,'occurrences':uses})
                bindings+=1
                if bindings>64:raise BridgeError('generalized binding budget exceeded')
                return n|{'value':rhs,'body':body},True
            v,changed=specialize(n['value'],env,ds,path+['value'])
            if changed:return n|{'value':v},True
            b,changed=specialize(n['body'],env|{n['name']['id']:inf(n['value'])},ds,path+['body']);return n|{'body':b},changed
        if tag=='with_data':
            b,c=specialize(n['body'],env,n['declarations'],path+['body']);return n|{'body':b},c
        if tag=='lambda':
            b,c=specialize(n['body'],env|{n['parameter']['id']:n['parameter_type']},ds,path+['body']);return n|{'body':b},c
        if tag=='type_lambda':
            b,c=specialize(n['body'],env,ds,path);return n|{'body':b},c
        if tag=='type_application':
            base,proofs=closed_type_spine(n);b,c=specialize(base,env,ds,path)
            for proof in proofs:b={'tag':'type_application','value':b,'witness':proof}
            return b,c
        if tag=='application':
            f,c=specialize(n['function'],env,ds,path+['function'])
            if c:return n|{'function':f},True
            a,c=specialize(n['argument'],env,ds,path+['argument']);return n|{'argument':a},c
        if tag=='letrec':
            if any(type_prefix(b['value'])[0]or b['type']['tag']=='forall'for b in n['bindings']):raise BridgeError('recursive polymorphic binding unsupported')
            scope=env|{b['name']['id']:b['type']for b in n['bindings']}
            for i,b in enumerate(n['bindings']):
                v,c=specialize(b['value'],scope,ds,path+['bindings',str(i),'value'])
                if c:return n|{'bindings':[x if j!=i else x|{'value':v}for j,x in enumerate(n['bindings'])]},True
            b,c=specialize(n['body'],scope,ds,path+['body']);return n|{'body':b},c
        if tag=='case':
            v,c=specialize(n['scrutinee'],env,ds,path+['scrutinee'])
            if c:return n|{'scrutinee':v},True
            subject=inf(n['scrutinee'])
            for i,a in enumerate(n['alternatives']):
                typ=raw_constructor_type(a['pattern']['constructor'],subject['arguments'],ds);fields=[]
                while typ['tag']=='arrow':fields.append(typ['from']);typ=typ['to']
                scope=env|{x['id']:t for x,t in zip(a['pattern']['fields'],fields)if x is not None}
                b,c=specialize(a['body'],scope,ds,path+['alternatives',str(i),'body'])
                if c:return n|{'alternatives':[x if j!=i else x|{'body':b}for j,x in enumerate(n['alternatives'])]},True
        return n,False
    result=node
    while True:
        result=direct(result);result,changed=specialize(result,{},[],[])
        if not changed:break
    def closed_type(t):
        if t['tag']in ('var','forall','bottom','bottom_kind','apply'):raise BridgeError('unresolved/nonmonomorphic annotation remains')
        if t['tag']=='arrow':closed_type(t['from']);closed_type(t['to'])
        elif t['tag']=='constructor':
            for a in t['arguments']:closed_type(a)
    def final(n):
        tag=n['tag']
        if tag in ('type_lambda','type_application'):raise BridgeError('type wrapper remains after closed-instance normalization')
        if tag=='lambda':closed_type(n['parameter_type']);final(n['body'])
        elif tag in ('constructor','primitive'):
            for t in n['arguments']:closed_type(t)
        elif tag=='application':final(n['function']);final(n['argument'])
        elif tag=='let':final(n['value']);final(n['body'])
        elif tag=='letrec':
            for b in n['bindings']:closed_type(b['type']);final(b['value'])
            final(n['body'])
        elif tag=='case':
            closed_type(n['result_type']);final(n['scrutinee'])
            for a in n['alternatives']:final(a['body'])
        elif tag=='with_data':final(n['body'])
    final(result)
    if term_skeleton(node)!=term_skeleton(result):raise BridgeError('closed normalization changed term/declaration skeleton')
    return result,steps


def validate_normalization(value):
    n=value['normalization']
    new_policy=n.get('policy')=='single-closed-instance/1'
    exact(n,{'policy','original_checked_type','original_checked_type_pretty','original_checked_term_pretty',
             'original_declaration_bindings','original_annotated','original_erased','normalized_annotated','steps',
             'original_rechecked','normalized_rechecked','root_type_alpha_equal','erasure_equal'}|
             ({'original_term_skeleton','normalized_term_skeleton'}if new_policy else set()),'normalization')
    for key in ('original_rechecked','normalized_rechecked','root_type_alpha_equal','erasure_equal'):
        if n[key] is not True:raise BridgeError('normalization recheck/equality guard not affirmed')
    validate_type(n['original_checked_type']);text(n['original_checked_type_pretty'],'original type pretty');text(n['original_checked_term_pretty'],'original term pretty')
    validate_inventory(n['original_declaration_bindings'])
    if type(n['steps']) is not list:raise BridgeError('normalization steps must be an array')
    for step in n['steps']:
        if type(step) is not dict:raise BridgeError('normalization step must be an object')
        if step.get('rule')=='erase_refl':
            exact(step,{'rule','witness'},'normalization step')
        elif step.get('rule')in ('instantiate_closed_int','instantiate_closed'):
            exact(step,{'rule','binder','bound','argument','witness'},'normalization step')
            integer(step['binder'],'normalization binder');validate_type(step['bound']);validate_type(step['argument'])
        elif step.get('rule')=='specialize_let':
            if not new_policy:raise BridgeError('specialization requires new policy')
            exact(step,{'rule','binding','type_binders','arguments','original_type','instantiated_type','occurrences'},'specialization step')
            name(step['binding'],'specialized binding');validate_type(step['original_type']);validate_type(step['instantiated_type'])
            if any(type(step[k])is not list for k in ['type_binders','arguments','occurrences']):raise BridgeError('specialization witness arrays required')
            for b in step['type_binders']:
                exact(b,{'id','bound'},'type binder');integer(b['id'],'type binder id');validate_type(b['bound'])
            for t in step['arguments']:validate_type(t)
            for occurrence in step['occurrences']:
                exact(occurrence,{'path','witnesses'},'occurrence')
                if type(occurrence['path'])is not list or type(occurrence['witnesses'])is not list:raise BridgeError('occurrence arrays required')
                for edge in occurrence['path']:text(edge,'occurrence edge')
                for proof in occurrence['witnesses']:validate_computation(proof)
            continue
        else:raise BridgeError('unknown normalization rule')
        validate_computation(step['witness'])
    original_projection=projection(n['original_annotated'],True,True)
    normalized_projection=projection(n['normalized_annotated'],True,True)
    validate_erased(n['original_erased'])
    if original_projection!=n['original_erased'] or normalized_projection!=n['original_erased'] or n['original_erased']!=value['erased']:
        raise BridgeError('original/normalized actual erased projections differ')
    if strip_data_evidence(n['normalized_annotated'])!=value['annotated']:
        raise BridgeError('normalized raw annotation differs from executable annotation')
    if not alpha_type_equal(n['original_checked_type'],value['checked_type']):raise BridgeError('normalization root types differ')
    has_if=contains_conditional(n['original_annotated'])
    parametric=has_parameterized_sum(n['original_annotated'])
    if new_policy and parametric:
        expected,steps=normalize_closed_instances_raw(n['original_annotated'])
        if n['original_term_skeleton']!=term_skeleton(n['original_annotated'])or n['normalized_term_skeleton']!=term_skeleton(n['normalized_annotated'])or n['original_term_skeleton']!=n['normalized_term_skeleton']:
            raise BridgeError('closed normalization declaration/term skeleton differs')
    elif n['policy']=='identity-no-conditional/1' and not has_if and not parametric:
        expected,steps=n['original_annotated'],[]
    elif n['policy']=='closed-int-standard-instantiation/1' and has_if and not parametric:
        expected,steps=normalize_conditional_raw(n['original_annotated'])
    else:raise BridgeError('normalization policy does not match original checked primitive inventory')
    if expected!=n['normalized_annotated'] or steps!=n['steps']:
        raise BridgeError('bounded normalization replay/step witness differs')


def projection(node, annotated=True, raw=False):
    if type(node) is not dict:raise BridgeError("runtime node must be object")
    tag=node.get("tag")
    recurse=lambda n:projection(n,annotated,raw)
    if tag in ('int64', 'bool'):
        exact(node, {'tag', 'value'}, tag)
        scalar_payload(tag, node['value'])
        return dict(node)
    if tag == 'primitive':
        exact(node, {'tag', 'id', 'name'} | ({'arguments'} if annotated else set()), tag)
        primitive_contract(node)
        if annotated:primitive_arguments(node,raw=raw)
        return {k:node[k] for k in ['tag', 'id', 'name']}
    if tag=="with_data" and annotated and raw:
        exact(node,{"tag","declarations","body"},tag);validate_declarations(node["declarations"])
        return recurse(node["body"])
    if tag in ("unit","var"):
        exact(node,{"tag"} | ({"name"} if tag=="var" else set()),tag)
        if tag=="var":name(node["name"],"var.name")
        return dict(node)
    if tag=="constructor":
        exact(node,{"tag","name"}|({"arguments"} if annotated else set()),tag)
        text(node["name"],"constructor.name")
        if annotated:
            if type(node["arguments"]) is not list:raise BridgeError("constructor arguments must be list")
            for t in node["arguments"]:validate_type(t)
        return {"tag":tag,"name":node["name"]}
    if tag=="lambda":
        exact(node,{"tag","parameter","body"}|({"parameter_type"} if annotated else set()),tag)
        name(node["parameter"],"lambda.parameter")
        if annotated:validate_type(node["parameter_type"])
        return {"tag":tag,"parameter":node["parameter"],"body":recurse(node["body"])}
    if tag=="application":
        exact(node,{"tag","function","argument"},tag)
        return {"tag":tag,"function":recurse(node["function"]),"argument":recurse(node["argument"])}
    if tag=="let":
        exact(node,{"tag","name","value","body"},tag);name(node["name"],"let.name")
        return {"tag":tag,"name":node["name"],"value":recurse(node["value"]),"body":recurse(node["body"])}
    if tag=="letrec":
        exact(node,{"tag","bindings","body"},tag)
        if type(node["bindings"]) is not list or not node["bindings"]:raise BridgeError("empty/invalid recursion bindings")
        bindings=[]
        for b in node["bindings"]:
            exact(b,{"name","value"}|({"type"} if annotated else set()),"recursive binding")
            name(b["name"],"recursive name")
            if annotated:validate_type(b["type"])
            bindings.append({"name":b["name"],"value":recurse(b["value"])})
        return {"tag":tag,"bindings":bindings,"body":recurse(node["body"])}
    if tag=="case":
        exact(node,{"tag","scrutinee","alternatives"}|({"result_type"} if annotated else set()),tag)
        if annotated:validate_type(node["result_type"])
        if type(node["alternatives"]) is not list:raise BridgeError("invalid alternatives")
        alternatives=[]
        for a in node["alternatives"]:
            exact(a,{"pattern","body"},"alternative");p=a["pattern"]
            exact(p,{"constructor","fields"},"pattern");text(p["constructor"],"pattern constructor")
            if type(p["fields"]) is not list:raise BridgeError("invalid pattern fields")
            for n in p["fields"]:
                if n is not None:name(n,"pattern field")
            alternatives.append({"pattern":p,"body":recurse(a["body"])})
        return {"tag":tag,"scrutinee":recurse(node["scrutinee"]),"alternatives":alternatives}
    if annotated and tag=="type_lambda":
        exact(node,{"tag","id","bound","body"},tag);integer(node["id"],"type id");validate_type(node["bound"])
        return recurse(node["body"])
    if annotated and tag=="type_application":
        exact(node,{"tag","value","witness"},tag);validate_computation(node["witness"])
        return recurse(node["value"])
    raise BridgeError("unsupported runtime syntax: "+str(tag))


def annotated_erasure(node):return projection(node,True)
def validate_erased(node):projection(node,False)


@dataclass(frozen=True)
class Envelope:
    """Validated transport only; does not assert that ordinary checking occurred."""
    canonical_json: str
    sha256: str

    def data(self) -> dict:
        return json.loads(self.canonical_json)


def parse_envelope(raw: str, *, manifest: dict | None = None) -> Envelope:
    if len(raw.encode("utf-8")) > MAX_BYTES:raise BridgeError("transport byte bound exceeded")
    try:
        value=json.loads(raw,object_pairs_hook=strict_pairs,
                         parse_constant=lambda x: (_ for _ in ()).throw(BridgeError("nonfinite JSON")))
    except (json.JSONDecodeError,RecursionError) as e:
        raise BridgeError("invalid/beyond-depth JSON transport") from e
    bounded(value)
    exact(value,{"format","producer","checked_type","checked_type_pretty","checked_term_pretty", "declaration_bindings","representation","annotated","erased","normalization"},"envelope")
    if value["format"]!="mlf-checked-recursion-export/6":raise BridgeError("unsupported export format")
    exact(value["producer"],{"source_commit","dependency_digest"},"producer")
    if manifest is None:manifest=json.loads((BASE/"validation/source-manifest.json").read_text())
    if value["producer"]!={k:manifest[k] for k in ("source_commit","dependency_digest")}:
        raise BridgeError("producer source identity mismatch (matching it is not proof of origin)")
    validate_type(value["checked_type"])
    text(value["checked_type_pretty"],"checked_type_pretty");text(value["checked_term_pretty"],"checked_term_pretty")
    inventory=value["declaration_bindings"]
    if not isinstance(inventory,dict):raise BridgeError("bad declaration inventory")
    if inventory.get("status")=="available":
        exact(inventory,{"status","bindings"},"bindings")
        if not isinstance(inventory["bindings"],list):raise BridgeError("bad binding list")
        for b in inventory["bindings"]:
            exact(b,{"name","type"},"binding");name(b["name"],"binding.name");validate_type(b["type"])
    elif inventory.get("status")=="unavailable":
        exact(inventory,{"status","diagnostic"},"bindings");text(inventory["diagnostic"],"bindings.diagnostic")
    else:raise BridgeError("unknown declaration inventory status")
    representation=value["representation"]
    exact(representation,{"builtin_unit","builtin_scalars","custom_datatypes","custom_sums","sum_instances"},"representation")
    if representation["builtin_unit"]!={"constructor":"()","datatype":"()","arity":0,"fields":[]}:
        raise BridgeError("invalid original builtin unit metadata")
    integer(representation["builtin_unit"]["arity"],"unit arity")
    expected_scalars=[{'datatype':name,'kind':{'tag':'star'},'arity':0,'runtime_shape':shape}
                      for name,shape in [('Int','#i64'),('Bool','#bool')]]
    if representation['builtin_scalars']!=expected_scalars:
        raise BridgeError('intrinsic scalar metadata differs from actual compiler contract')
    for item in representation['builtin_scalars']:
        integer(item['arity'],'scalar arity')
    validate_erased(value["erased"])
    if annotated_erasure(value["annotated"]) != value["erased"]:
        raise BridgeError("annotated metadata projection differs from actual X.erase transport")
    validate_normalization(value)
    validate_declaration_metadata(value)
    Representation(representation)
    canonical=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return Envelope(canonical,hashlib.sha256(canonical.encode()).hexdigest())


# Representation compatibility only, never an ordinary-checking replacement.
@dataclass(frozen=True)
class Nominal:
    """Disjoint from builtin Unit and callable tuple shapes, even for data Unit."""
    name: str
    arguments: tuple = ()

Shape = str | tuple | Nominal

def strip(node):
    while node["tag"] in ("type_lambda","type_application"):
        node=node["body"] if node["tag"]=="type_lambda" else node["value"]
    return node


def constructor_spine(node):
    arguments=[];cursor=strip(node)
    while cursor["tag"]=="application":
        arguments.append(cursor["argument"]);cursor=strip(cursor["function"])
    if cursor["tag"]=="constructor":return cursor,list(reversed(arguments))
    return None


def free_vars(node):
    node=strip(node);tag=node["tag"]
    if tag in ("unit","constructor","int64","bool","primitive"):return set()
    if tag=="var":return {node["name"]["id"]}
    if tag=="lambda":return free_vars(node["body"])-{node["parameter"]["id"]}
    if tag=="application":return free_vars(node["function"])|free_vars(node["argument"])
    if tag=="let":return free_vars(node["value"])|(free_vars(node["body"])-{node["name"]["id"]})
    if tag=="letrec":
        local={b["name"]["id"] for b in node["bindings"]}
        return (set().union(*(free_vars(b["value"]) for b in node["bindings"]))|free_vars(node["body"]))-local
    if tag=="case":
        answer=free_vars(node["scrutinee"])
        for a in node["alternatives"]:
            answer|=free_vars(a["body"])-{n["id"] for n in a["pattern"]["fields"] if n is not None}
        return answer
    raise BridgeError("unsupported free-variable node")


# Primitive/source identity sets come from the hash-bound ordinary Data module.
# NEW conservative guard also rejects internal builtin constructor shadows; the
# ordinary DataEnv map can shadow these, but this transport does not admit them.
# Actual K.check/DataEnv validation remains authority, not this compatibility gate.
SOURCE_TUPLES={'('+','*(n-1)+')' for n in range(2,65)}
RESERVED_DATATYPES={'()', '[]','True','False','Integer','AsyncScope','Completion','AsyncSubscription',
    'ST','STArray','Int','Double','Bool','String','MLFLegacyUnit','IntArray','DoubleArray','ByteArray',
    'IntTable','IO','MLFCallStack','MLFStackFrame','MLFStackEvidence','IOError','Char'} | SOURCE_TUPLES
RESERVED_CONSTRUCTORS={'()','[]',':','True','False','MLFLegacyUnit','MLFStackFrame','MLFStackEvidence'} | SOURCE_TUPLES

def has_parameterized_sum(node):
    return node.get('tag')=='with_data' and any(d['parameters'] and len(d['constructors'])>1 for d in node['declarations'])

def declaration_views(declarations,node):
    """Replay complete templates and one concrete instance per nominal owner."""
    validate_declarations(declarations);records=[];templates=[];by_name={};by_constructor={};names=set();constructors=set()
    def record_field(f):
        if f['tag']=='applied' and f['arguments']==[]:return {'tag':'constructor','name':f['name'],'arguments':[]}
        if f['tag']=='function':return {'tag':'arrow','from':record_field(f['from']),'to':record_field(f['to'])}
        raise BridgeError('record fields require existing closed nominal/arrow grammar')
    for index,d in enumerate(declarations):
        tn=d['name'];cs=d['constructors']
        if tn in RESERVED_DATATYPES or tn in names:raise BridgeError('duplicate/reserved declaration family')
        names.add(tn)
        if not cs:raise BridgeError('empty declaration family')
        for c in cs:
            if c['name']in RESERVED_CONSTRUCTORS or c['name']in constructors:raise BridgeError('duplicate/reserved constructor')
            constructors.add(c['name'])
        if len(cs)==1:
            if d['parameters']:raise BridgeError('parameterized record declaration unsupported')
            c=cs[0];fields=[record_field(f)for f in c['fields']]
            records.append({'datatype':tn,'constructor':c['name'],'arity':len(fields),'fields':fields});continue
        if len(cs)>64:raise BridgeError('sum variant bound exceeded')
        parameters=[{'name':p,'kind':{'tag':'star'}}if d['tag']=='data'else p for p in d['parameters']]
        if len(parameters)>8 or len({p['name']for p in parameters})!=len(parameters)or any(p['kind']!={'tag':'star'}for p in parameters):raise BridgeError('sum parameters require distinct bounded Star formals')
        if any(len(c['fields'])>32 for c in cs):raise BridgeError('sum field bound exceeded')
        template={'declaration_index':index,'datatype':tn,'parameters':parameters,'constructors':[
            {'constructor':c['name'],'arity':len(c['fields']),'fields':c['fields']}for c in cs]}
        templates.append(template);by_name[tn]=template
        for c in cs:by_constructor[c['name']]=template
    if len(templates)>64:raise BridgeError('sum instance bound exceeded')
    arguments={t['datatype']:[]for t in templates if not t['parameters']}
    def register(t,args):
        if len(args)!=len(t['parameters'])or not all(closed_scalar_argument(a)for a in args):raise BridgeError('sum instance arguments require exact closed Int/Bool vector')
        n=t['datatype']
        if n in arguments and arguments[n]!=args:raise BridgeError('mixed instances of one nominal declaration')
        arguments[n]=args
    def scan_type(t):
        if t['tag']=='constructor':
            if t['name']in by_name:register(by_name[t['name']],t['arguments'])
            for a in t['arguments']:scan_type(a)
        elif t['tag']=='arrow':scan_type(t['from']);scan_type(t['to'])
        elif t['tag']=='forall':scan_type(t['bound']);scan_type(t['body'])
        elif t['tag']=='apply':scan_type(t['function']);scan_type(t['argument'])
    def scan(n):
        tag=n['tag']
        if tag=='with_data':scan(n['body'])
        elif tag=='constructor':
            if n['name']in by_constructor:register(by_constructor[n['name']],n['arguments'])
            for t in n['arguments']:scan_type(t)
        elif tag=='primitive':
            for t in n['arguments']:scan_type(t)
        elif tag=='lambda':scan_type(n['parameter_type']);scan(n['body'])
        elif tag=='type_lambda':scan_type(n['bound']);scan(n['body'])
        elif tag=='type_application':scan(n['value'])
        elif tag=='application':scan(n['function']);scan(n['argument'])
        elif tag=='let':scan(n['value']);scan(n['body'])
        elif tag=='letrec':
            for b in n['bindings']:scan_type(b['type']);scan(b['value'])
            scan(n['body'])
        elif tag=='case':
            scan_type(n['result_type']);scan(n['scrutinee'])
            for a in n['alternatives']:scan(a['body'])
    scan(node)
    done={}
    while len(done)!=len(arguments):
        for template in templates:
            name_=template['datatype']
            if name_ not in arguments or name_ in done:continue
            args=arguments[name_];params=dict(zip([p['name']for p in template['parameters']],args));members=[]
            for c in template['constructors']:
                fields=[]
                for raw in c['fields']:
                    if raw['tag']not in ('parameter','applied'):raise BridgeError('sum payload outside closed scalar/instance grammar')
                    typ=raw_field_type(raw,params)
                    if typ['tag']!='constructor':raise BridgeError('sum field is not a closed nominal type')
                    if typ['name']in ('Int','Bool'):
                        if typ['arguments']:raise BridgeError('intrinsic scalar field has arguments')
                    elif typ['name']in by_name:register(by_name[typ['name']],typ['arguments'])
                    else:raise BridgeError('sum fields require Int/Bool/registered sum instance')
                    fields.append(typ)
                members.append({'constructor':c['constructor'],'arity':len(fields),'fields':fields})
            done[name_]={'declaration_index':template['declaration_index'],'datatype':name_,'arguments':args,'constructors':members}
    if len(done)!=len(templates):raise BridgeError('unused unresolved parameterized declaration')
    return records,templates,[done[t['datatype']]for t in templates]

def validate_sum_metadata_schema(metadata):
    for lane in ['custom_sums','sum_instances']:
        values=metadata[lane]
        if type(values)is not list:raise BridgeError('sum metadata must be an array')
        for d in values:
            exact(d,{'declaration_index','datatype','constructors'}|({'parameters'}if lane=='custom_sums'else {'arguments'}),'sum metadata')
            if integer(d['declaration_index'],'declaration index')<0:raise BridgeError('negative declaration index')
            text(d['datatype'],'datatype')
            if type(d['constructors'])is not list:raise BridgeError('sum constructors must be an array')
            if lane=='custom_sums':
                if type(d['parameters'])is not list:raise BridgeError('sum parameters must be an array')
                for p in d['parameters']:
                    exact(p,{'name','kind'},'sum formal');text(p['name'],'formal name');validate_kind(p['kind'])
            else:
                if type(d['arguments'])is not list:raise BridgeError('sum arguments must be an array')
                for a in d['arguments']:validate_type(a)
            for c in d['constructors']:
                exact(c,{'constructor','arity','fields'},'sum variant metadata');text(c['constructor'],'constructor')
                if type(c['fields'])is not list or integer(c['arity'],'variant arity')!=len(c['fields']):raise BridgeError('sum metadata field arity differs')
                for f in c['fields']:(validate_field if lane=='custom_sums'else validate_type)(f)

def validate_declaration_metadata(value):
    validate_sum_metadata_schema(value['representation'])
    originals=[]
    for key in ['original_annotated','normalized_annotated']:
        raw=value['normalization'][key];declarations=raw['declarations']if raw['tag']=='with_data'else []
        def no_nested_data(x):
            if type(x)is dict:
                if x.get('tag')=='with_data':raise BridgeError('nested declaration scope unsupported')
                for y in x.values():no_nested_data(y)
            elif type(x)is list:
                for y in x:no_nested_data(y)
        no_nested_data(raw['body']if raw['tag']=='with_data'else raw)
        records,templates,instances=declaration_views(declarations,value['normalization']['normalized_annotated'])
        m=value['representation']
        if records!=m['custom_datatypes']or templates!=m['custom_sums']or instances!=m['sum_instances']:
            raise BridgeError('complete generic declaration/closed instance projection differs')
        originals.append(declarations)
    if originals[0]!=originals[1]:raise BridgeError('normalization changed generic data declarations')


class Representation:
    def __init__(self,metadata):
        ds=metadata["custom_datatypes"];ss=metadata['sum_instances']
        if type(ds) is not list or type(ss) is not list:raise BridgeError("invalid datatype/family list")
        self.datatypes={};self.constructors={};self.records={};self.sums={}
        def identity(tn,cn):
            if tn in RESERVED_DATATYPES or cn in RESERVED_CONSTRUCTORS:raise BridgeError('reserved nominal identity')
            if cn in self.constructors:raise BridgeError('duplicate cross-family constructor identity')
        for d in ds:
            exact(d,{"datatype","constructor","arity","fields"},"datatype")
            tn=text(d["datatype"],"datatype name");cn=text(d["constructor"],"constructor name")
            identity(tn,cn)
            if tn in self.datatypes:raise BridgeError('duplicate datatype identity')
            if type(d["fields"]) is not list or integer(d["arity"],"arity")!=len(d["fields"]):raise BridgeError("datatype field arity mismatch")
            for t in d["fields"]:validate_type(t)
            derived=dict(d);derived.update(shape=Nominal(tn),family_kind='record')
            self.datatypes[tn]=derived;self.constructors[cn]=derived;self.records[derived["shape"]]=derived
        if len(ss)>64:raise BridgeError('sum family bound exceeded')
        # First register nominal families; recursive fields are finite references.
        for d in ss:
            exact(d,{'declaration_index','datatype','arguments','constructors'},'sum instance');integer(d['declaration_index'],'declaration index');tn=text(d['datatype'],'family name')
            if tn in RESERVED_DATATYPES or tn in self.datatypes:raise BridgeError('duplicate/reserved sum family')
            if type(d['constructors']) is not list or not 2<=len(d['constructors'])<=64:raise BridgeError('sum projection requires 2..64 declared constructors')
            if type(d['arguments'])is not list or not all(closed_scalar_argument(a)for a in d['arguments']):raise BridgeError('invalid sum instance arguments')
            derived=dict(d);derived.update(shape=Nominal(tn,tuple(json.dumps(a,sort_keys=True,separators=(',',':'))for a in d['arguments'])),family_kind='sum');self.datatypes[tn]=derived;self.sums[derived['shape']]=derived
        # Then authenticate every variant's complete ordered field vector.
        for d in ss:
            tn=d['datatype'];derived=self.datatypes[tn]
            for i,c in enumerate(d['constructors']):
                exact(c,{'constructor','arity','fields'},'sum constructor');cn=text(c['constructor'],'sum constructor name');identity(tn,cn)
                if type(c['fields']) is not list or integer(c['arity'],'sum arity')!=len(c['fields']) or len(c['fields'])>32:
                    raise BridgeError('sum field arity/bound mismatch')
                shapes=[]
                for typ in c['fields']:
                    validate_type(typ)
                    if typ['tag']!='constructor':raise BridgeError('sum field must be closed nominal/scalar')
                    name=typ['name']
                    if name not in ('Int','Bool') and (name not in self.datatypes or self.datatypes[name]['family_kind']!='sum'):
                        raise BridgeError('sum fields admit Int/Bool/registered sum only')
                    shapes.append(self.type_shape(typ))
                self.constructors[cn]={'datatype':tn,'constructor':cn,'arity':c['arity'],'fields':c['fields'],'field_shapes':shapes,
                    'shape':derived['shape'],'family_kind':'sum','variant_id':i,'arguments':d['arguments'],'declaration_index':d['declaration_index']}

        for d in self.records.values():d["field_shapes"]=[self.type_shape(t) for t in d["fields"]]

    def type_shape(self,t):
        if t.get("tag")=="constructor" and not t["arguments"]:
            if t["name"]=="()":return "Unit"
            if t["name"]=="Int":return "#i64"
            if t["name"]=="Bool":return "#bool"
        if t.get("tag")=="constructor" and t["name"]in self.datatypes:
            d=self.datatypes[t["name"]]
            if t["arguments"]!=d.get("arguments",[]):raise BridgeError("nominal type arguments differ from exact closed instance")
            return d["shape"]
        if t.get("tag")=="arrow":return (self.type_shape(t["from"]),self.type_shape(t["to"]))
        raise BridgeError("unsupported runtime representation: closed Unit/Int64/Bool/nominal/arrow types only")

    def shape_of(self,node,env):
        node=strip(node);tag=node["tag"]
        if tag=="unit":return "Unit"
        if tag in ('int64', 'bool'):
            scalar_payload(tag, node['value'])
            return '#i64' if tag == 'int64' else '#bool'
        if tag == 'primitive':
            specification = primitive_contract(node)
            primitive_arguments(node)
            if node['id']==13:return ('#bool',('#i64',('#i64','#i64')))
            return ('#i64', ('#i64', specification[1]))
        if tag=="constructor":
            if node["name"] not in self.constructors:raise BridgeError("constructor missing original datatype metadata")
            d=self.constructors[node["name"]]
            if node["arguments"]!=d.get("arguments",[]):raise BridgeError("constructor arguments differ from actual instance")
            shape=d["shape"]
            for arg in reversed(d["field_shapes"]):shape=(arg,shape)
            return shape
        if tag=="var":
            ident=node["name"]["id"]
            if ident not in env:raise BridgeError("free erased variable")
            return env[ident]
        if tag=="lambda":
            ident=node["parameter"]["id"]
            if ident in env:raise BridgeError("duplicate in-scope binder identity")
            parameter=self.type_shape(node["parameter_type"])
            return (parameter,self.shape_of(node["body"],env|{ident:parameter}))
        if tag=="application":
            f=self.shape_of(node["function"],env);a=self.shape_of(node["argument"],env)
            if type(f) is not tuple or f[0]!=a:raise BridgeError("representation mismatch at application")
            return f[1]
        if tag=="let":
            ident=node["name"]["id"]
            if ident in env:raise BridgeError("duplicate in-scope let identity")
            return self.shape_of(node["body"],env|{ident:self.shape_of(node["value"],env)})
        if tag=="letrec":
            ids=[b["name"]["id"] for b in node["bindings"]]
            if len(set(ids))!=len(ids) or set(ids)&set(env):raise BridgeError("duplicate recursive identity")
            inner=env|{b["name"]["id"]:self.type_shape(b["type"]) for b in node["bindings"]}
            for b in node["bindings"]:
                if self.shape_of(b["value"],inner)!=inner[b["name"]["id"]]:raise BridgeError("recursive representation mismatch")
            return self.shape_of(node["body"],inner)
        if tag=="case":
            shape=self.shape_of(node["scrutinee"],env)
            if shape in self.sums:
                metadata=self.sums[shape];expected={c['constructor'] for c in metadata['constructors']}
                observed=[];result=self.type_shape(node['result_type'])
                if result!='#i64':raise BridgeError('nominal sum case requires actual Int result')
                for a in node['alternatives']:
                    p=a['pattern'];cn=p['constructor'];observed.append(cn)
                    if cn not in expected:raise BridgeError('case constructor does not belong to scrutinee family')
                    variant=self.constructors[cn]
                    if len(p['fields'])!=variant['arity']:raise BridgeError('sum pattern field arity mismatch')
                    ids=[n['id'] for n in p['fields'] if n is not None]
                    if len(ids)!=len(set(ids)) or set(ids)&set(env):raise BridgeError('duplicate sum pattern identity')
                    inner=env|{n['id']:field for n,field in zip(p['fields'],variant['field_shapes']) if n is not None}
                    if self.shape_of(a['body'],inner)!=result:raise BridgeError('sum case result representation mismatch')
                if len(observed)!=len(set(observed)) or set(observed)!=expected:raise BridgeError('sum case must cover exact complete family once')
                return result
            if shape not in self.records:raise BridgeError("case requires declared nominal datatype")
            if len(node["alternatives"])!=1:raise BridgeError("record case requires exactly one alternative")
            a=node["alternatives"][0];d=self.records[shape];p=a["pattern"]
            if p["constructor"]!=d["constructor"] or len(p["fields"])!=d["arity"]:raise BridgeError("case metadata mismatch")
            ids=[n["id"] for n in p["fields"] if n is not None]
            if len(set(ids))!=len(ids) or set(ids)&set(env):raise BridgeError("duplicate pattern identity")
            inner=env|{n["id"]:s for n,s in zip(p["fields"],d["field_shapes"]) if n is not None}
            result=self.type_shape(node["result_type"])
            if self.shape_of(a["body"],inner)!=result:raise BridgeError("case result representation mismatch")
            return result
        raise BridgeError("unsupported representation node")
