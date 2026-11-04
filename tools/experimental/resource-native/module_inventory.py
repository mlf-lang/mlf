"""Normalized executable census -> complete reachable nominal runtime views.

The full original declaration context is syntax/identity checked but NOT eagerly
runtime-admitted. Only complete used families are admitted. This is not XMLF type
inference/checking and never drops a field or invents a nominal instance.
"""
import module_projection as projection

POLICY = 'normalized-concrete-family-views/1'
SOURCE_TUPLES = {'('+','*(n-1)+')' for n in range(2,65)}
# Same conservative source/builtin identity guards as the accepted export/6
# transport; compiler-side D.validateDeclarations/lookup remains authority.
RESERVED_DATATYPES = {'()', '[]','True','False','Integer','AsyncScope','Completion','AsyncSubscription',
    'ST','STArray','Int','Double','Bool','String','MLFLegacyUnit','IntArray','DoubleArray','ByteArray',
    'IntTable','IO','MLFCallStack','MLFStackFrame','MLFStackEvidence','IOError','Char'} | SOURCE_TUPLES
RESERVED_CONSTRUCTORS = {'()','[]',':','True','False','MLFLegacyUnit','MLFStackFrame','MLFStackEvidence'} | SOURCE_TUPLES


class InventoryError(ValueError):
    pass


def fail(message):
    raise InventoryError(message)


def _type(name, arguments=()):
    return {'tag':'constructor','name':name,'arguments':list(arguments)}


def _parameters(d):
    return [{'name':n,'kind':{'tag':'star'}}for n in d['parameters']] if d['tag']=='data' else d['parameters']


def _scalar(t):
    return (type(t)is dict and set(t)=={'tag','name','arguments'} and
            t['tag']=='constructor' and t['name']in ('Int','Bool') and t['arguments']==[])


def _field_type(raw, parameters, *, record):
    """Iterative exact existing raw field grammar, not application normalization."""
    values={};work=[(False,raw)]
    while work:
        done,node=work.pop();tag=node['tag']
        if not done:
            if record:
                if tag=='applied' and node['arguments']==[]:children=[]
                elif tag=='function':children=[node['from'],node['to']]
                else:fail('record fields require existing closed Applied nominal[]/Function grammar')
            else:
                if tag=='parameter':children=[]
                elif tag=='applied':children=node['arguments']
                else:fail('sum fields require existing Parameter/Applied grammar')
            work.append((True,node));work.extend((False,c)for c in reversed(children));continue
        if tag=='parameter':
            if node['name']not in parameters:fail('unknown declared field parameter')
            result=parameters[node['name']]
        elif tag=='applied':result=_type(node['name'],[values[id(a)]for a in node['arguments']])
        else:result={'tag':'arrow','from':values[id(node['from'])],'to':values[id(node['to'])]}
        values[id(node)]=result
    return values[id(raw)]


def _arrow(a, b):
    return {'tag':'arrow','from':a,'to':b}


def _argument_codes(arguments):
    if not all(_scalar(a) for a in arguments):
        fail('view arguments are not exact closed intrinsic Int/Bool')
    return tuple(0 if a['name']=='Int' else 1 for a in arguments)


def _view_key(ref):
    """Actual complete nominal identity, never physical-layout equivalence."""
    return (ref['declaration_index'], ref['datatype'], _argument_codes(ref['arguments']))


def _view_order(ref):
    return (ref['declaration_index'], _argument_codes(ref['arguments']))


def _logical_cases(body, checked_type, by_name, by_constructor, registered,
                   members_by_view, root_path, case_paths):
    """Independently infer bounded monomorphic logical types, iteratively.

    No supplied case witness is an inference premise. Complete view/member tables
    here were derived above from the raw declarations, not from producer metadata.
    This is compatibility replay; actual ordinary scoped checking remains authority.
    """
    cases={};results=[];work=[('visit',body,{},root_path)]

    def equal_type(a,b,label):
        if not projection.exact_equal(a,b):fail(label+' exact logical type mismatch')

    def view(n,args):
        if n not in by_name:fail('logical nominal type lacks actual declaration')
        index,d=by_name[n]
        reference={'declaration_index':index,'datatype':n,'arguments':args}
        key=_view_key(reference)
        if key not in registered:fail('case/type has no proven concrete instance after closure')
        # Key includes both original declaration index and resolved identity.
        if not projection.exact_equal(registered[key],reference):fail('nominal view identity mismatch')
        return reference,d,members_by_view[key]

    def bind(env,n,t):
        if n['id'] in env:fail('logical term binder already in scope')
        return env|{n['id']:t}

    def primitive(node):
        ident=node['id'];arguments=node['arguments'];integer=_type('Int')
        names={8:'addInt',9:'subInt',14:'mulInt',10:'eqInt',11:'ltInt'}
        if ident in names:
            if node['name']!=names[ident] or arguments:fail('logical primitive identity/type argument mismatch')
            return _arrow(integer,_arrow(integer,_type('Bool') if ident in (10,11) else integer))
        if ident==13 and node['name']=='ifThenElse':
            if not projection.exact_equal(arguments,[integer]):fail('logical conditional requires actual Int type argument')
            return _arrow(_type('Bool'),_arrow(integer,_arrow(integer,integer)))
        fail('logical primitive outside exact admitted whitelist')

    while work:
        operation,*data=work.pop()
        if operation=='lambda_done':
            results.append(_arrow(data[0],results.pop()));continue
        if operation=='application_done':
            actual=results.pop();function=results.pop()
            if function['tag']!='arrow':fail('logical application of nonfunction')
            equal_type(function['from'],actual,'application argument')
            results.append(function['to']);continue
        if operation=='let_rhs':
            node,env,path=data;actual=results.pop()
            work.append(('visit',node['body'],bind(env,node['name'],actual),path+'.body'));continue
        if operation in ('check_recursive','check_arm'):
            equal_type(data[0],results.pop(),operation);continue
        if operation=='case_done':results.append(data[0]);continue
        if operation=='case_subject':
            node,env,path=data;scrutinee=results.pop();result_type=node['result_type']
            if scrutinee['tag']!='constructor':fail('case scrutinee is not a closed nominal logical type')
            if scrutinee['name']=='()' and scrutinee['arguments']==[]:
                reference=None;declaration=None;members=[{'constructor':'()','arity':0,'fields':[]}]
            else:
                reference,declaration,members=view(scrutinee['name'],scrutinee['arguments'])
            if declaration is not None and len(declaration['constructors'])>1:
                equal_type(result_type,_type('Int'),'SUM case result')
            variants={c['constructor']:(i,c)for i,c in enumerate(members)}
            arms=[];children=[];seen=set()
            for i,alternative in enumerate(node['alternatives']):
                pattern=alternative['pattern']
                if pattern['tag']!='constructor':fail('logical default case unsupported')
                cn=pattern['constructor']
                if cn not in variants or cn in seen:fail('case alternatives do not match exact scrutinee view')
                seen.add(cn);variant,member=variants[cn]
                if len(pattern['fields'])!=member['arity']:fail('case binding count differs from complete view fields')
                inner=env;fields=[]
                for field_index,(n,typ)in enumerate(zip(pattern['fields'],member['fields'])):
                    fields.append({'field_index':field_index,'name':n,'type':typ})
                    if n is not None:inner=bind(inner,n,typ)
                arms.append({'constructor':cn,'variant_index':variant,'fields':fields})
                children.append((alternative['body'],inner,path+f'.alternatives[{i}].body'))
            if seen!=set(variants):fail('case omits a complete view variant')
            if path in cases:fail('duplicate logical case path')
            cases[path]={'path':path,'scrutinee_type':scrutinee,'view':reference,'arms':arms}
            work.append(('case_done',result_type))
            for child,inner,child_path in reversed(children):
                work.append(('check_arm',result_type));work.append(('visit',child,inner,child_path))
            continue
        if operation!='visit':fail('unknown logical replay continuation')
        node,env,path=data;tag=node['tag']
        if tag=='var':
            if node['name']['id']not in env:fail('logical variable is out of scope')
            results.append(env[node['name']['id']])
        elif tag=='int64':results.append(_type('Int'))
        elif tag=='bool':results.append(_type('Bool'))
        elif tag=='primitive':results.append(primitive(node))
        elif tag=='constructor':
            cn=node['name'];args=node['arguments']
            if cn=='()':
                if args:fail('Unit constructor cannot have type arguments')
                results.append(_type('()'));continue
            if cn not in by_constructor:fail('logical constructor missing actual owner')
            _,declaration,variant,_=by_constructor[cn]
            reference,_,members=view(declaration['name'],args);member=members[variant]
            if member['constructor']!=cn:fail('logical constructor declaration position changed')
            typ=_type(reference['datatype'],reference['arguments'])
            for field in reversed(member['fields']):typ=_arrow(field,typ)
            results.append(typ)
        elif tag=='lambda':
            work.append(('lambda_done',node['parameter_type']))
            work.append(('visit',node['body'],bind(env,node['parameter'],node['parameter_type']),path+'.body'))
        elif tag=='application':
            work.append(('application_done',));work.append(('visit',node['argument'],env,path+'.argument'));work.append(('visit',node['function'],env,path+'.function'))
        elif tag=='let':
            work.append(('let_rhs',node,env,path));work.append(('visit',node['value'],env,path+'.value'))
        elif tag=='letrec':
            inner=env
            for binding in node['bindings']:inner=bind(inner,binding['name'],binding['type'])
            work.append(('visit',node['body'],inner,path+'.body'))
            for i,binding in reversed(list(enumerate(node['bindings']))):
                work.append(('check_recursive',binding['type']));work.append(('visit',binding['value'],inner,path+f'.bindings[{i}].value'))
        elif tag=='case':
            work.append(('case_subject',node,env,path));work.append(('visit',node['scrutinee'],env,path+'.scrutinee'))
        else:fail('unknown/nonmonomorphic logical replay term')
    if len(results)!=1:fail('logical replay result stack mismatch')
    equal_type(results[0],checked_type,'checked root')
    if set(cases)!=set(case_paths)or len(cases)!=len(case_paths):fail('logical case census differs from syntax traversal')
    return [cases[path]for path in case_paths]


def derive_inventory(declarations, normalized_total_term, checked_type):
    """Return records/templates/canonical view rows and complete replay witness.

    Actual source origin/full XMLF checking is a separate mandatory prerequisite.
    This function derives everything from raw syntax and never uses supplied rows.
    """
    projection.validate_raw_term({'tag':'with_data','declarations':declarations,'body':{'tag':'int64','value':0}})
    projection.validate_raw_term(normalized_total_term,require_closed=True)
    projection.validate_raw_term({'tag':'lambda','parameter':{'id':0,'hint':'$inventory-type-check'},'parameter_type':checked_type,'body':{'tag':'int64','value':0}})
    if normalized_total_term['tag']=='with_data':
        if not projection.exact_equal(normalized_total_term['declarations'],declarations):fail('normalized declaration context differs')
        body=normalized_total_term['body'];root_path='root.body'
    else:
        if declarations:fail('complete declarations missing from normalized term')
        body=normalized_total_term;root_path='root'
    by_name={};by_constructor={}
    for index,d in enumerate(declarations):
        n=d['name']
        if n in RESERVED_DATATYPES or n in by_name:fail('duplicate/reserved declaration family')
        by_name[n]=(index,d)
        for variant,c in enumerate(d['constructors']):
            cn=c['name']
            if cn in RESERVED_CONSTRUCTORS or cn in by_constructor:fail('duplicate/reserved cross-family constructor')
            by_constructor[cn]=(index,d,variant,c)
    registry=[];registered={};sum_count=0

    def ref(n,args):return {'declaration_index':by_name[n][0],'datatype':n,'arguments':args}

    def register(n,args):
        nonlocal sum_count
        if n not in by_name:fail('nominal identity absent from complete declarations')
        _,d=by_name[n];constructors=d['constructors'];parameters=_parameters(d)
        if not constructors or len(constructors)>64:fail('used family requires1..64 complete variants')
        is_sum=len(constructors)>1
        if is_sum:
            if len(parameters)>8 or any(p['kind']!={'tag':'star'}for p in parameters):fail('used sum formals require at most8 Star parameters')
            if len(args)!=len(parameters)or not all(_scalar(a)for a in args):fail('sum arguments require exact closed Int/Bool vector')
            if any(len(c['fields'])>32 for c in constructors):fail('used sum exceeds32 complete fields')
        elif parameters or args:fail('parameterized record outside existing route')
        reference=ref(n,args);key=_view_key(reference)
        if key in registered:return
        if is_sum:
            if sum_count>=64:fail('used concrete SUM view bound exceeds64')
            sum_count+=1
        registered[key]=reference;registry.append(reference)

    def scan_type(t):
        pending=[t]
        while pending:
            node=pending.pop();tag=node['tag']
            if tag=='arrow':pending.extend((node['to'],node['from']))
            elif tag=='constructor':
                n=node['name'];args=node['arguments']
                if n in ('Int','Bool','()'):
                    if args:fail('intrinsic runtime type cannot have arguments')
                elif n in by_name:register(n,args)
                else:fail('retained type has no supported concrete representation')
                pending.extend(reversed(args))
            else:fail('unresolved/nonmonomorphic representation-bearing annotation')

    scan_type(checked_type)
    case_paths=[];pending=[('term',body,root_path)]
    while pending:
        action,node,path=pending.pop()
        if action=='type':scan_type(node);continue
        tag=node['tag']
        if tag=='lambda':pending.extend((('term',node['body'],path+'.body'),('type',node['parameter_type'],None)))
        elif tag=='application':pending.extend((('term',node['argument'],path+'.argument'),('term',node['function'],path+'.function')))
        elif tag=='let':pending.extend((('term',node['body'],path+'.body'),('term',node['value'],path+'.value')))
        elif tag=='letrec':
            pending.append(('term',node['body'],path+'.body'))
            for i,b in reversed(list(enumerate(node['bindings']))):pending.extend((('term',b['value'],path+f'.bindings[{i}].value'),('type',b['type'],None)))
        elif tag=='constructor':
            cn=node['name'];args=node['arguments']
            if cn=='()':
                if args:fail('Unit constructor cannot have type arguments')
            elif cn in by_constructor:
                _,d,_,_=by_constructor[cn];register(d['name'],args)
            else:fail('retained constructor absent from exact admitted owner context')
            for a in args:scan_type(a)
        elif tag=='primitive':
            for a in node['arguments']:scan_type(a)
        elif tag=='case':
            # Preorder cases are distinct from seed ordering: result annotation,
            # scrutinee, then source-order bodies determines new seed insertion.
            case_paths.append(path)
            for i,alt in reversed(list(enumerate(node['alternatives']))):
                if alt['pattern']['tag']!='constructor':fail('retained default case outside exhaustive constructor route')
                pending.append(('term',alt['body'],path+f'.alternatives[{i}].body'))
            pending.extend((('term',node['scrutinee'],path+'.scrutinee'),('type',node['result_type'],None)))
        elif tag in ('type_lambda','type_application'):fail('type wrapper remains at normalized runtime census boundary')
        elif tag=='with_data':fail('nested data context outside module runtime census policy')
        elif tag in ('string','double'):fail('retained String/Double outside target fragment')
        elif tag not in ('var','int64','bool'):fail('unknown retained executable constructor')
    seeds=list(registry);members_by_view={};edges=[];cursor=0
    while cursor<len(registry):
        item=registry[cursor];cursor+=1;n=item['datatype'];_,d=by_name[n]
        is_sum=len(d['constructors'])>1;parameters={p['name']:a for p,a in zip(_parameters(d),item['arguments'])};members=[]
        for variant,c in enumerate(d['constructors']):
            fields=[]
            for field_index,raw in enumerate(c['fields']):
                typ=_field_type(raw,parameters,record=not is_sum);fields.append(typ)
                positions=[(typ,[])]
                while positions:
                    ft,path=positions.pop()
                    if ft['tag']=='arrow'and not is_sum:
                        positions.extend(((ft['to'],path+['to']),(ft['from'],path+['from'])));continue
                    if ft['tag']!='constructor':fail('payload has no closed concrete field representation')
                    target=ft['name'];args=ft['arguments']
                    if target in ('Int','Bool')or(target=='()'and not is_sum):
                        if args:fail('scalar/Unit payload has type arguments')
                    else:
                        if target not in by_name:fail('payload nominal owner not in complete context')
                        if is_sum and len(by_name[target][1]['constructors'])<=1:fail('sum fields require Int/Bool/SUM, not Unit/record/arrow')
                        register(target,args)
                        edges.append({'source':item,'variant_index':variant,'field_index':field_index,'type_path':path,'target':ref(target,args)})
            members.append({'constructor':c['name'],'arity':len(fields),'fields':fields})
        members_by_view[_view_key(item)]=members
    cases=_logical_cases(body,checked_type,by_name,by_constructor,registered,members_by_view,root_path,case_paths)
    selected=sorted({r['declaration_index']for r in registry});records=[];templates=[];instances=[]
    for index in selected:
        d=declarations[index];n=d['name']
        if len(d['constructors'])==1:
            c=members_by_view[_view_key(ref(n,[]))][0];records.append({'datatype':n,'constructor':c['constructor'],'arity':c['arity'],'fields':c['fields']})
        else:
            templates.append({'declaration_index':index,'datatype':n,'parameters':_parameters(d),
                              'constructors':[{'constructor':c['name'],'arity':len(c['fields']),'fields':c['fields']}for c in d['constructors']]})
    for item in sorted((r for r in registry if len(declarations[r['declaration_index']]['constructors'])>1),key=_view_order):
        instances.append(dict(item,view_index=len(instances),constructors=members_by_view[_view_key(item)]))
    edges.sort(key=lambda e:(_view_order(e['source']),e['variant_index'],e['field_index'],e['type_path']))
    witness={'policy':POLICY,'seed_instances':seeds,'closure_instances':registry,'closure_edges':edges,'case_obligations':cases,
             'selected_declaration_indices':selected,'evidence_only_declaration_indices':[i for i in range(len(declarations))if i not in set(selected)]}
    return records,templates,instances,witness


def verify_inventory(declarations, normalized_total_term, checked_type, records, templates, instances, witness):
    actual=derive_inventory(declarations,normalized_total_term,checked_type)
    for name,supplied,expected in zip(('records','templates','instances','witness'),(records,templates,instances,witness),actual):
        if not projection.exact_equal(supplied,expected):fail('runtime inventory '+name+' differs from exact normalized concrete-family views')
    return actual[3]
