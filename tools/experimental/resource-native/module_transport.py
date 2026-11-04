"""Strict opt-in captured-module envelope replay; NOT an ordinary checker.

The whole module envelope remains the canonical planner binding. Lossless original
syntax is never routed through the old runtime whitelist. Only independently
projected, type-normalized retained syntax reaches that unchanged strict route.
Genuine compiled origin and snapshot/source custody are external prerequisites;
producer booleans and a fabricated envelope cannot establish them.
"""
import hashlib
import json
from pathlib import Path

import transport as fragment
import module_projection as projection
import module_inventory as inventory
import module_custody as custody

FORMAT = 'mlf-checked-module-export/2'
MAX_BYTES = 32 * 1024 * 1024
BASE = Path(__file__).resolve().parent
TOP_KEYS = {'format','producer','module_custody','original','projection',
            'normalization','runtime_inventory','representation','annotated',
            'erased','checked_type'}
ORIGINAL_KEYS = {'checked_type','annotated','erased','source_erased','binder_origins',
                 'ordinary_whole_check_passed','root_type_alpha_equal','source_erasure_equal'}
PROJECTION_KEYS = {'policy','original_checked_type','projected_checked_type',
                   'projected_annotated','projected_erased','steps','original_rechecked',
                   'projected_rechecked','root_type_alpha_equal','declarations_equal',
                   'erased_projection_equal'}


class ModuleTransportError(fragment.BridgeError):
    pass


def fail(message):
    raise ModuleTransportError(message)


def equal(actual, expected, label):
    if not projection.exact_equal(actual,expected):fail(label+' differs')


def envelope_budget(value):
    """Bound total duplicated evidence, independently of per-artifact AST caps."""
    work=[(False,value,1)];active=set();cells=containers=0
    while work:
        leaving,item,depth=work.pop()
        if leaving:active.remove(id(item));continue
        cells+=1
        if cells>projection.MAX_NODES*32 or depth>projection.MAX_DEPTH:
            fail('module envelope cell/depth budget exceeded')
        kind=type(item)
        if kind in (dict,list):
            containers+=1
            if containers>projection.MAX_NODES*8:fail('module envelope container budget exceeded')
            if id(item)in active:fail('cyclic module JSON')
            active.add(id(item));work.append((True,item,depth))
            if kind is dict:
                for key,child in item.items():
                    fragment.text(key,'module JSON key');work.append((False,child,depth+1))
            else:work.extend((False,child,depth+1)for child in item)
        elif kind is str:fragment.text(item,'module JSON string')
        elif kind is int:
            if not projection.MIN_I64<=item<=projection.MAX_I64:fail('module JSON integer outside signed64')
        elif kind not in (bool,type(None)):fail('noncanonical module JSON scalar')


def strict_lane_bound(value):
    """Iteratively enforce the old lane's unchanged cell/depth budget first.

    This protects recursive legacy validators; no recursion-limit changes and no
    use of total-original allowances to enlarge target admission are permitted.
    """
    work=[(value,0)];count=0
    while work:
        item,depth=work.pop();count+=1
        if count>fragment.MAX_NODES or depth>fragment.MAX_DEPTH:
            fail('retained fragment exceeds unchanged strict cell/depth contract')
        if type(item)is dict:work.extend((v,depth+1)for v in item.values())
        elif type(item)is list:work.extend((v,depth+1)for v in item)


def fragment_raw(term, *, erased=False):
    """Exact total->legacy vocabulary translation, never term optimization.

    Unit changes spelling only; constructor patterns lose their explicit tag.
    Full declarations/proofs remain byte-structurally represented. Unsupported
    retained forms reject, and no source/default arm is silently discarded.
    """
    projection.validate_raw_term(term,erased=erased,require_closed=True)
    values={};work=[(False,term)]
    while work:
        done,node=work.pop();tag=node['tag']
        if not done:
            if tag in ('string','double','evidence_hole'):
                fail('unsupported retained total syntax: '+tag)
            if tag=='case':
                if any(a['pattern']['tag']!='constructor'for a in node['alternatives']):
                    fail('retained default pattern is outside the strict fragment')
                children=[node['scrutinee']]+[a['body']for a in node['alternatives']]
            elif tag in ('lambda','type_lambda','with_data'):children=[node['body']]
            elif tag=='type_application':children=[node['value']]
            elif tag=='application':children=[node['function'],node['argument']]
            elif tag=='let':children=[node['value'],node['body']]
            elif tag=='letrec':children=[b['value']for b in node['bindings']]+[node['body']]
            else:children=[]
            work.append((True,node));work.extend((False,c)for c in reversed(children));continue
        result=dict(node)
        if tag=='constructor' and node['name']=='()':
            if not erased and node['arguments']!=[]:fail('Unit constructor has type arguments')
            result={'tag':'unit'}
        elif tag in ('lambda','type_lambda','with_data'):result['body']=values[id(node['body'])]
        elif tag=='type_application':result['value']=values[id(node['value'])]
        elif tag=='application':
            result.update(function=values[id(node['function'])],argument=values[id(node['argument'])])
        elif tag=='let':result.update(value=values[id(node['value'])],body=values[id(node['body'])])
        elif tag=='letrec':
            result['bindings']=[dict(b,value=values[id(b['value'])])for b in node['bindings']]
            result['body']=values[id(node['body'])]
        elif tag=='case':
            result['scrutinee']=values[id(node['scrutinee'])]
            result['alternatives']=[{'pattern':{'constructor':a['pattern']['constructor'],'fields':a['pattern']['fields']},
                                     'body':values[id(a['body'])]}for a in node['alternatives']]
        values[id(node)]=result
    return values[id(term)]


def _declarations(term):
    return term['declarations']if term['tag']=='with_data'else []


def _validate_type(t):
    projection.validate_raw_term({'tag':'lambda','parameter':{'id':0,'hint':'$module-root-type'},
        'parameter_type':t,'body':{'tag':'int64','value':0}})
    strict_lane_bound(t)
    fragment.validate_type(t)


def _validate_value(value, manifest):
    # Complete total JSON bounded before any recursive strict operation. Syntax
    # category validation below remains mandatory; this is not a generic decoder.
    envelope_budget(value)
    fragment.exact(value,TOP_KEYS,'module envelope')
    if value['format']!=FORMAT:fail('unsupported module export format')
    fragment.exact(value['producer'],{'source_commit','dependency_digest'},'module producer')
    expected={k:manifest[k]for k in ('source_commit','dependency_digest')}
    equal(value['producer'],expected,'historical producer source anchor (not proof of origin)')
    original=value['original'];projected=value['projection'];normal=value['normalization']
    fragment.exact(original,ORIGINAL_KEYS,'module original')
    fragment.exact(projected,PROJECTION_KEYS,'module projection')
    fragment.exact(normal,{'fragment','raw_normalized'},'module normalization')
    for record,keys in [(original,('ordinary_whole_check_passed','root_type_alpha_equal','source_erasure_equal')),
                        (projected,('original_rechecked','projected_rechecked','root_type_alpha_equal','declarations_equal','erased_projection_equal'))]:
        for key in keys:
            if record[key]is not True:fail('module checked guard not affirmed: '+key)
    if projected['policy']!='outer-lazy-spine/1':fail('unsupported outer projection policy')
    for term in (original['annotated'],projected['projected_annotated'],normal['raw_normalized']):
        projection.validate_raw_term(term,require_closed=True)
    for term in (original['erased'],original['source_erased'],projected['projected_erased']):
        projection.validate_raw_term(term,erased=True,require_closed=True)
    equal(original['erased'],original['source_erased'],'actual source erasure')
    projection.replay_projection(original['annotated'],original['erased'],
        projected['projected_annotated'],projected['projected_erased'],projected['steps'])
    declarations=_declarations(original['annotated'])
    equal(_declarations(projected['projected_annotated']),declarations,'projected full declarations')
    equal(_declarations(normal['raw_normalized']),declarations,'normalized full declarations')
    for t in (original['checked_type'],projected['original_checked_type'],projected['projected_checked_type'],value['checked_type']):
        _validate_type(t)
    equal(projected['original_checked_type'],original['checked_type'],'projection original checked type custody')
    for t in (projected['projected_checked_type'],value['checked_type']):
        if not fragment.alpha_type_equal(original['checked_type'],t):fail('module root types are not alpha equal')
    # Actual source/resolver/constraint association is independently replayed;
    # the compiled producer remains authority for text parsing and whole checking.
    custody.validate_custody(value['module_custody'],original)
    old_original=fragment_raw(projected['projected_annotated'])
    old_normalized=fragment_raw(normal['raw_normalized'])
    old_erased=fragment_raw(projected['projected_erased'],erased=True)
    lane={'normalization':normal['fragment'],'annotated':value['annotated'],
          'erased':value['erased'],'checked_type':value['checked_type']}
    # Bound BOTH supplied and derived retained forms before recursive equality,
    # normalization, alpha comparison or representation constructors.
    strict_lane_bound({'lane':lane,'representation':value['representation']})
    for derived in (old_original,old_normalized,old_erased):strict_lane_bound(derived)
    if type(normal['fragment'])is not dict:fail('normalization fragment must be an object')
    fragment.exact(normal['fragment'],{
        'policy','original_checked_type','original_checked_type_pretty','original_checked_term_pretty',
        'original_declaration_bindings','original_annotated','original_erased','normalized_annotated','steps',
        'original_rechecked','normalized_rechecked','root_type_alpha_equal','erasure_equal'}|
        ({'original_term_skeleton','normalized_term_skeleton'}if normal['fragment'].get('policy')=='single-closed-instance/1'else set()),
        'module normalization fragment')
    equal(normal['fragment']['original_annotated'],old_original,'normalization projected raw input')
    equal(normal['fragment']['normalized_annotated'],old_normalized,'normalization total output')
    equal(normal['fragment']['original_erased'],old_erased,'normalization projected erasure')
    equal(normal['fragment']['original_checked_type'],projected['projected_checked_type'],'normalization checked input type custody')
    fragment.validate_normalization(lane)
    fragment.validate_erased(value['erased'])
    equal(fragment.annotated_erasure(value['annotated']),value['erased'],'strict annotated/erased linkage')
    equal(fragment_raw(projection.erase_total(normal['raw_normalized']),erased=True),value['erased'],'total normalized erasure/strict linkage')
    metadata=value['representation']
    fragment.exact(metadata,{'builtin_unit','builtin_scalars','custom_datatypes','custom_sums','sum_instances'},'module representation')
    equal(metadata['builtin_unit'],{'constructor':'()','datatype':'()','arity':0,'fields':[]},'actual builtin Unit metadata')
    equal(metadata['builtin_scalars'],[{'datatype':n,'kind':{'tag':'star'},'arity':0,'runtime_shape':s}
                                      for n,s in [('Int','#i64'),('Bool','#bool')]],'actual intrinsic scalar metadata')
    inventory.verify_inventory(declarations,normal['raw_normalized'],value['checked_type'],
        metadata['custom_datatypes'],metadata['custom_sums'],metadata['sum_instances'],value['runtime_inventory'])
    fragment.validate_multi_view_metadata_schema(metadata)
    fragment.MultiViewRepresentation(metadata)
    # Do NOT call old validate_declaration_metadata/declaration_views: those
    # eagerly require all full-context declarations to have runtime layouts.
    return value


def parse_module_envelope(raw, *, manifest=None):
    """Return existing Envelope binding the COMPLETE accepted module JSON."""
    try:
        if type(raw)is not str:fail('module transport requires JSON text')
        if len(raw.encode('utf-8'))>MAX_BYTES:fail('module transport exceeds32MiB byte bound')
        value=json.loads(raw,object_pairs_hook=fragment.strict_pairs,
            parse_constant=lambda _:fail('nonfinite module JSON'),
            parse_float=lambda _:fail('nonintegral module JSON number'))
        if manifest is None:manifest=json.loads((BASE/'validation/source-manifest.json').read_text())
        _validate_value(value,manifest)
        canonical=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        return fragment.Envelope(canonical,hashlib.sha256(canonical.encode('utf-8')).hexdigest())
    except ModuleTransportError:raise
    except (fragment.BridgeError,projection.ProjectionError,inventory.InventoryError,custody.CustodyError,
            UnicodeError,json.JSONDecodeError,RecursionError,KeyError,TypeError,ValueError)as exc:
        raise ModuleTransportError('module envelope rejected: '+str(exc))from exc
