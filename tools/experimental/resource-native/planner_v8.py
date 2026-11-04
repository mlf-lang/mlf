"""Opt-in coarse-owned lowering of independently replayed shared fragments.

This is not K/source admission. Raw proof/normalization evidence is freshly
replayed at this boundary; the returned IR candidate still requires the unchanged
independent IR8 resource checker and emitter. Old planner/default paths are not
imported or changed. No ordinary lambda cloning, beta reduction, identity-name
recognition, nominal fallback, or per-type RHS expansion is performed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import module_shared_transport as transport

MAX_WORK = 1_000_000
MAX_INSTRUCTIONS = 10_000
MAX_CODES = 2048
MAX_TYPES = 4096
MAX_CAPTURES = 64
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
SCALARS = {'Int': ('scalar', '#i64'), 'Bool': ('scalar', '#bool')}
PRIMITIVES = {8: ('addInt', SCALARS['Int']), 9: ('subInt', SCALARS['Int']),
              10: ('eqInt', SCALARS['Bool']), 11: ('ltInt', SCALARS['Bool']),
              14: ('mulInt', SCALARS['Int'])}


class PlanningError(ValueError):
    """Explicit unsupported fragment or bounded candidate-generation failure."""


def require(ok, message):
    if not ok:
        raise PlanningError(message)


def address(path):
    return {'stage': 'normalized', 'path': list(path)}


def arrow(a, b):
    # Ordinary source arrows establish this conservative exact contract only.
    # It is part of equality/interning, never inferred from a function's name.
    return ('arrow', a, b, 'repeat', 'unknown')


@dataclass(frozen=True)
class Reference:
    variable: str
    logical: tuple
    carrier: int | None = None


@dataclass(frozen=True)
class SchemeReference:
    variable: str
    definition: int


@dataclass
class Block:
    root: str
    name: str | None
    body: list
    prefix: tuple = ()
    scope: str | None = None

    def path(self, index):
        return {'root': self.root, 'name': self.name, 'segments': list(self.prefix + (index,))}


class Planner:
    def __init__(self, fragment):
        self.fragment = fragment
        self.root = fragment['raw_normalized']
        self.work = self.instructions = self.variables = self.code_count = 0
        self.types = {}; self.type_names = {}; self.signatures = {}; self.signature_names = {}
        self.functions = {}; self.codes = {}; self.schemes = {}; self.instantiations = {}
        self.instantiation_names = {}
        self.definitions = fragment['polymorphism']['definitions']
        self.def_by_path = {tuple(d['binding_source']['path']): d for d in self.definitions}
        self.def_by_binder = {d['binding']['id']: d for d in self.definitions}
        self.uses = {tuple(u['source']['path']): u for u in fragment['polymorphism']['uses']}
        self.scopes = {}; self.definition_types = {}; self.use_pairs = {}; self.use_types = {}
        self.term_map = {}; self.scheme_map = []; self.use_map = []; self.carrier_map = []; self.allocation_map = []
        for d in self.definitions:
            scope = 'S' + str(d['id'])
            self.scopes[scope] = {p['id']: ('rigid', scope, p['rigid_index']) for p in d['prefix']}
            logical = self.logical(d['body_type'], scope)
            require(logical[0] == 'arrow', 'Scheme body must remain callable')
            self.definition_types[d['id']] = logical
            self.schemes[scope] = {'parameters': len(d['prefix']), 'body': self.type_name(logical)}
        for path, u in self.uses.items():
            d = self.definitions[u['definition']]
            vector = tuple(self.logical(t, None) for t in u['arguments'])
            require(len(vector) == len(d['prefix']) and all(t[0] == 'scalar' for t in vector),
                    'complete closed Int/Bool vector required')
            pair = (d['binding']['id'], vector)
            self.use_pairs[path] = pair
            typ = self.substitute(self.definition_types[d['id']], 'S' + str(d['id']), vector)
            require(typ == self.logical(u['instantiated_type'], None), 'replayed use result differs')
            self.use_types[path] = typ

    def tick(self, amount=1):
        require(amount <= MAX_WORK - self.work, 'planner work limit')
        self.work += amount

    def fresh(self, prefix='v'):
        self.tick(); self.variables += 1
        return prefix + str(self.variables)

    def logical(self, raw, scope, depth=0):
        self.tick(); require(depth < 32, 'logical type depth limit')
        if raw['tag'] == 'constructor':
            require(raw['name'] in SCALARS and raw['arguments'] == [], 'nominal or non-scalar type unsupported')
            return SCALARS[raw['name']]
        if raw['tag'] == 'var':
            require(scope in self.scopes and raw['id'] in self.scopes[scope], 'foreign/open logical type')
            return self.scopes[scope][raw['id']]
        require(raw['tag'] == 'arrow', 'rank1 monotype required')
        return arrow(self.logical(raw['from'], scope, depth+1), self.logical(raw['to'], scope, depth+1))

    def substitute(self, typ, scope, vector):
        self.tick()
        if typ[0] == 'rigid':
            require(typ[1] == scope, 'foreign Scheme rigid')
            return vector[typ[2]]
        if typ[0] == 'arrow':
            return ('arrow', self.substitute(typ[1], scope, vector), self.substitute(typ[2], scope, vector), typ[3], typ[4])
        return typ

    def type_name(self, typ):
        self.tick()
        if typ in self.type_names:
            return self.type_names[typ]
        if typ[0] == 'scalar': row = {'tag': 'closed', 'layout': typ[1]}
        elif typ[0] == 'rigid': row = {'tag': 'rigid', 'scheme': typ[1], 'index': typ[2]}
        else:
            require(typ[0] == 'arrow' and typ[3:] == ('repeat', 'unknown'), 'unsupported callable contract')
            row = {'tag': 'arrow', 'argument': self.type_name(typ[1]), 'result': self.type_name(typ[2]),
                   'protocol': typ[3], 'result_identity': typ[4]}
        require(len(self.types) < MAX_TYPES, 'type count limit')
        name = 'T' + str(len(self.types)); self.type_names[typ] = name; self.types[name] = row
        return name

    def layout(self, typ):
        return '^' + self.type_name(typ)

    def signature(self, typ):
        self.tick(); require(typ[0] == 'arrow', 'callable required')
        if typ not in self.signature_names:
            name = 'A' + str(len(self.signatures)); self.signature_names[typ] = name
            self.signatures[name] = {'argument': self.layout(typ[1]), 'result': self.layout(typ[2]),
                                     'protocol': typ[3], 'result_identity': typ[4]}
        return self.signature_names[typ]

    def add(self, block, source=None, logical=None, **instruction):
        self.tick(); require(self.instructions < MAX_INSTRUCTIONS, 'instruction limit')
        path = block.path(len(block.body)); self.instructions += 1; block.body.append(instruction)
        if instruction['op'] in ('scalar', 'closure', 'application', 'thunk', 'prim2'):
            require(source is not None and logical is not None, 'allocation correspondence missing')
            require(len(self.allocation_map) + self.code_count < MAX_CODES, 'combined Site/Code limit')
            self.allocation_map.append({'source': address(source), 'instruction': path,
                                        'role': instruction['op'], 'type_scope': block.scope,
                                        'logical_type': self.type_name(logical)})
        return path

    def release(self, ref, block):
        self.add(block, op='drop', value=ref.variable)

    def term(self, node, path, role='ordinary'):
        self.tick(); require(path not in self.term_map, 'ordinary source occurrence emitted more than once')
        row = {'source': address(path), 'tag': node['tag'], 'role': role}
        if node['tag'] in ('var', 'let'): row['binder'] = node['name']['id']
        elif node['tag'] == 'lambda': row['binder'] = node['parameter']['id']
        self.term_map[path] = row

    def instantiation(self, pair):
        if pair not in self.instantiation_names:
            require(len(self.instantiations) < 1024, 'complete-vector instantiation limit')
            d = self.def_by_binder[pair[0]]
            name = 'U' + str(len(self.instantiations)); self.instantiation_names[pair] = name
            self.instantiations[name] = {'scheme': 'S' + str(d['id']),
                                        'arguments': [self.type_name(t) for t in pair[1]]}
        return self.instantiation_names[pair]

    def acquire_view(self, pair, env, views, block):
        self.tick(); paths = []
        source = views.get(pair)
        if source is not None:
            ref = Reference(self.fresh(), source.logical)
            paths.append(self.add(block, op='retain', out=ref.variable, value=source.variable))
            require(source.carrier is not None, 'saved view lacks its lexical carrier')
            return ref, paths, {'kind': 'captured', 'carrier': source.carrier, 'capture': source.variable}
        source = env.get(pair[0]); d = self.def_by_binder[pair[0]]
        require(isinstance(source, SchemeReference) and source.definition == d['id'], 'shared view unavailable in lexical scope')
        owned = self.fresh(); result = self.fresh()
        paths.append(self.add(block, op='retain', out=owned, value=source.variable))
        paths.append(self.add(block, op='instantiate', out=result, value=owned, instantiation=self.instantiation(pair)))
        logical = self.substitute(self.definition_types[d['id']], 'S' + str(d['id']), pair[1])
        return Reference(result, logical), paths, {'kind': 'scheme', 'definition': d['id']}

    def needed(self, node, path, bound=frozenset()):
        """Transitive free lexical binders AND complete-vector shared views.

        A Scheme introduced inside this carrier is local, not a capture. Stop
        at its closed generic RHS; the fragment checker already rejects external
        captures there. Never erase type applications with the old free_vars.
        """
        mono = set(); pairs = {}
        def visit(n, p, local):
            self.tick(); tag = n['tag']
            if tag == 'type_application':
                require(p in self.uses, 'unmapped type application')
                key = self.use_pairs[p]
                if key[0] not in local: pairs.setdefault(key, []).append(self.uses[p]['id'])
                return
            if tag == 'var':
                if n['name']['id'] not in local: mono.add(n['name']['id'])
                return
            if tag == 'lambda':
                visit(n['body'], p+('body',), local | {n['parameter']['id']}); return
            if tag == 'let':
                if p not in self.def_by_path: visit(n['value'], p+('value',), local)
                visit(n['body'], p+('body',), local | {n['name']['id']}); return
            if tag == 'application':
                visit(n['function'], p+('function',), local); visit(n['argument'], p+('argument',), local); return
            if tag == 'with_data': visit(n['body'], p+('body',), local); return
            require(tag in ('int64', 'bool', 'primitive'), 'unsupported carrier syntax')
        visit(node, path, bound)
        require(len(mono)+len(pairs) <= MAX_CAPTURES, 'carrier capture count exceeds 64')
        return mono, pairs

    def captures(self, node, path, env, views, block, scope, kind, code, bound=frozenset()):
        mono, pairs = self.needed(node, path, bound)
        actual = {}; contracts = {}; inner = {}; saved = {}; temps = []
        carrier = {'carrier': len(self.carrier_map), 'source': address(path), 'kind': kind,
                   'ir_code': code, 'type_scope': scope, 'mono_captures': [], 'view_captures': []}
        self.carrier_map.append(carrier)
        for ident in sorted(mono):
            ref = env.get(ident); require(isinstance(ref, Reference), 'Scheme/bare or unavailable ordinary capture')
            name = self.fresh('capture'); actual[name] = ref.variable
            contracts[name] = {'layout': self.layout(ref.logical), 'relation': 'down'}
            inner[ident] = Reference(name, ref.logical)
            carrier['mono_captures'].append({'binder': ident, 'capture': name, **contracts[name]})
        for pair in sorted(pairs):
            ref, creation, source = self.acquire_view(pair, env, views, block); temps.append(ref)
            name = self.fresh('view'); actual[name] = ref.variable
            contracts[name] = {'layout': self.layout(ref.logical), 'relation': 'down'}
            saved[pair] = Reference(name, ref.logical, carrier['carrier'])
            d = self.def_by_binder[pair[0]]
            carrier['view_captures'].append({'definition': d['id'], 'binder': pair[0],
                'arguments': [self.type_name(t) for t in pair[1]], 'occurrences': pairs[pair],
                'capture': name, 'source_view': source, 'creation': creation, **contracts[name]})
        return actual, contracts, inner, saved, temps, carrier

    def code_name(self, prefix):
        self.tick(); require(self.code_count + len(self.allocation_map) < MAX_CODES, 'combined Site/Code limit')
        self.code_count += 1; return prefix + str(self.code_count)

    def emit(self, node, path, env, views, home, block, scope):
        self.tick(); tag = node['tag']
        if tag == 'with_data':
            require(not path, 'only outer evidence declarations supported')
            return self.emit(node['body'], path+('body',), env, views, home, block, scope)
        if tag == 'type_application':
            require(path in self.uses, 'unmapped shared use')
            u = self.uses[path]; basepath = tuple(u['variable']['path'])
            base = self.root
            for part in basepath: base = base[part]
            self.term(base, basepath, 'shared-use')
            ref, creation, source = self.acquire_view(self.use_pairs[path], env, views, block)
            self.use_map.append({'use': u['id'], 'source': address(path), 'definition': u['definition'],
                                 'arguments': [self.type_name(t) for t in self.use_pairs[path][1]],
                                 'creation': creation, 'source_view': source})
            require(ref.logical == self.use_types[path], 'captured full-vector view mismatch')
            return ref
        # Saturated builtin scalar operations remain delayed complete operand
        # graphs. This is checked primitive-ID lowering, never user-code inlining.
        if tag == 'application':
            head = node; hp = path; args = []; spine = []
            while head['tag'] == 'application':
                spine.append((head,hp)); args.append((head['argument'],hp+('argument',)))
                head = head['function']; hp += ('function',)
            if head['tag'] == 'primitive':
                require(scope is None, 'generic primitive body unsupported')
                for n,p in spine: self.term(n,p,'primitive-spine')
                self.term(head,hp,'primitive')
                return self.primitive(node,path,head,list(reversed(args)),env,views,home,block)
        self.term(node,path)
        if tag in ('int64','bool'):
            typ = SCALARS['Int' if tag=='int64' else 'Bool']; out = self.fresh()
            self.add(block,path,typ,op='scalar',out=out,**{'in':home},kind='i64' if tag=='int64' else 'bool',value=node['value'])
            return Reference(out,typ)
        if tag == 'var':
            ref = env.get(node['name']['id']); require(isinstance(ref,Reference), 'ordinary variable cannot be Scheme')
            out=self.fresh(); self.add(block,op='retain',out=out,value=ref.variable)
            return Reference(out,ref.logical)
        if tag == 'let':
            d = self.def_by_path.get(path)
            if d is not None:
                require(scope is None and d['free_term_bindings']==[], 'nested/external generic definition')
                scheme='S'+str(d['id']); out=self.fresh('shared')
                child=Block(block.root,block.name,[],block.prefix+(len(block.body),'body'),scheme)
                cursor=self.root
                for part in d['rhs_cursor']['path']: cursor=cursor[part]
                result=self.emit(cursor,tuple(d['rhs_cursor']['path']),{}, {}, '$home',child,scheme)
                require(result.logical==self.definition_types[d['id']], 'generic RHS actual result type differs')
                seal=self.add(child,op='seal',value=result.variable)
                intro=self.add(block,op='generalize',out=out,**{'in':home},scheme=scheme,body=child.body)
                ref=SchemeReference(out,d['id'])
                self.scheme_map.append({'definition':d['id'],'binder':d['binding']['id'],'scheme':scheme,
                    'generalize':intro,'seal':seal,'rhs_cursor':d['rhs_cursor'],'result_owner':result.variable})
            else:
                ref=self.emit(node['value'],path+('value',),env,views,home,block,scope)
            result=self.emit(node['body'],path+('body',),env|{node['name']['id']:ref},views,home,block,scope)
            self.release(ref,block); return result
        if tag == 'lambda':
            name=self.code_name('F')
            actual,contracts,inner,saved,temps,carrier=self.captures(node,path,env,views,block,scope,'lambda',name)
            parameter=self.fresh('argument'); parameter_type=self.logical(node['parameter_type'],scope)
            inner[node['parameter']['id']]=Reference(parameter,parameter_type)
            callback=Block('function',name,[],scope=scope)
            result=self.emit(node['body'],path+('body',),inner,saved,'$home',callback,scope)
            for ref in list(inner.values())+list(saved.values()): self.release(ref,callback)
            self.add(callback,op='return',value=result.variable)
            typ=arrow(parameter_type,result.logical)
            self.functions[name]={'signature':self.signature(typ),'parameter':parameter,'captures':contracts,
                                  'body':callback.body,'type_scope':scope}
            out=self.fresh(); publication=self.add(block,path,typ,op='closure',out=out,**{'in':home},function=name,captures=actual)
            for row in carrier['view_captures']: row['creation'].append(publication)
            for row,ref in zip(carrier['view_captures'],temps):
                release=self.add(block,op='drop',value=ref.variable)
                # One pair temp per view capture, in deterministic pair order.
                row['creation'].append(release)
            return Reference(out,typ)
        if tag == 'application':
            fn=self.emit(node['function'],path+('function',),env,views,home,block,scope)
            arg=self.emit(node['argument'],path+('argument',),env,views,home,block,scope)
            require(fn.logical[0]=='arrow' and fn.logical[1]==arg.logical, 'complete ordinary callable argument mismatch')
            out=self.fresh(); typ=fn.logical[2]
            self.add(block,path,typ,op='application',out=out,**{'in':home},function=fn.variable,argument=arg.variable)
            self.release(fn,block); self.release(arg,block); return Reference(out,typ)
        raise PlanningError('unsupported planning constructor: '+tag)

    def delayed(self,node,path,env,views,home,block,kind):
        name=self.code_name('C')
        actual,contracts,inner,saved,temps,carrier=self.captures(node,path,env,views,block,None,kind,name)
        cb=Block('thunk',name,[]); result=self.emit(node,path,inner,saved,'$home',cb,None)
        require(result.logical==SCALARS['Int'], 'conditional branches require Int')
        for ref in list(inner.values())+list(saved.values()): self.release(ref,cb)
        self.add(cb,op='return',value=result.variable)
        self.codes[name]={'result':self.layout(result.logical),'captures':contracts,'body':cb.body,'type_scope':None}
        out=self.fresh(); publication=self.add(block,path,result.logical,op='thunk',out=out,**{'in':home},code=name,captures=actual)
        for row,ref in zip(carrier['view_captures'],temps):
            row['creation'].append(publication); row['creation'].append(self.add(block,op='drop',value=ref.variable))
        return Reference(out,result.logical)

    def primitive(self,node,path,head,args,env,views,home,block):
        conditional=head['id']==13
        require((conditional and head['name']=='ifThenElse' and len(args)==3) or
                (head['id'] in PRIMITIVES and head['name']==PRIMITIVES[head['id']][0] and len(args)==2),
                'primitive must be directly and fully saturated')
        name=self.code_name('C'); typ=SCALARS['Int'] if conditional else PRIMITIVES[head['id']][1]
        actual,contracts,inner,saved,temps,carrier=self.captures(node,path,env,views,block,None,'conditional' if conditional else 'primitive',name)
        cb=Block('thunk',name,[])
        left=self.emit(*args[0],inner,saved,'$home',cb,None); ready=self.fresh()
        require(left.logical==(SCALARS['Bool'] if conditional else SCALARS['Int']), 'primitive left type')
        self.add(cb,op='force',out=ready,value=left.variable)
        result=self.fresh()
        if conditional:
            yes=self.delayed(*args[1],inner,saved,'$home',cb,'conditional-then')
            no=self.delayed(*args[2],inner,saved,'$home',cb,'conditional-else')
            self.add(cb,op='select_i64',out=result,**{'in':'$home'},condition=ready,**{'then':yes.variable,'else':no.variable})
        else:
            right=self.emit(*args[1],inner,saved,'$home',cb,None); ready_right=self.fresh()
            require(right.logical==SCALARS['Int'], 'primitive right type')
            self.add(cb,op='force',out=ready_right,value=right.variable)
            self.add(cb,path,typ,op='prim2',out=result,**{'in':'$home'},primitive=head['name'],left=ready,right=ready_right)
            self.add(cb,op='drop',value=ready_right)
        self.add(cb,op='drop',value=ready)
        for ref in list(inner.values())+list(saved.values()): self.release(ref,cb)
        self.add(cb,op='return',value=result)
        self.codes[name]={'result':self.layout(typ),'captures':contracts,'body':cb.body,'type_scope':None}
        out=self.fresh(); publication=self.add(block,path,typ,op='thunk',out=out,**{'in':home},code=name,captures=actual)
        for row,ref in zip(carrier['view_captures'],temps):
            row['creation'].append(publication); row['creation'].append(self.add(block,op='drop',value=ref.variable))
        return Reference(out,typ)

    def finish(self):
        block=Block('entry',None,[]); self.add(block,op='new_root',out='root',imports=[])
        result=self.emit(self.root,(),{}, {},'root',block,None)
        require(result.logical in SCALARS.values(), 'entry requires closed scalar result')
        require(result.logical==self.logical(self.fragment['checked_type'],None), 'fragment root result differs')
        ready=self.fresh(); self.add(block,op='force',out=ready,value=result.variable)
        self.add(block,op='drop',value='root'); self.add(block,op='finish_scalar',value=ready)
        expected={tuple(r['normalized']['path']):r['tag'] for r in self.fragment['term_correspondence']}
        require({p:r['tag'] for p,r in self.term_map.items()}==expected, 'ordinary node coverage differs from independent correspondence')
        require(sorted(r['use'] for r in self.use_map)==list(range(len(self.uses))), 'missing/repeated lowered shared occurrence')
        program={'version':8,'layouts':{},'families':{},'signatures':self.signatures,'types':self.types,
                 'schemes':self.schemes,'instantiations':self.instantiations,'functions':self.functions,
                 'codes':self.codes,'entry':block.body}
        source_map={'scheme_map':self.scheme_map,'use_map':self.use_map,'carrier_map':self.carrier_map,
                    'allocation_map':self.allocation_map,'term_map':list(self.term_map.values())}
        encoded=json.dumps(program,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        result={'program':program,'binding':{'status':'candidate-not-resource-checked','fragment_only':True,
                'source_admitted':False,'ordinary_K_checked':False,'mode':'coarse-owned',
                'input_sha256':hashlib.sha256(json.dumps(self.fragment['input_annotated'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
                'candidate_sha256':hashlib.sha256(encoded.encode()).hexdigest(),'source_map':source_map,
                'work':self.work,'instructions':self.instructions}}
        require(len(json.dumps(result,ensure_ascii=False).encode('utf-8'))<=MAX_OUTPUT_BYTES, 'planner output byte limit')
        return result


def plan_fragment(projected_annotated, *, fragment=None):
    """Fresh proof replay, then isolated candidate lowering, never source custody.

    Supplying a fragment is not an authority shortcut: all fields are recomputed
    and compared by validate_shared_fragment. Caller objects are not mutated.
    Every execution caller must independently resource-check the returned raw IR.
    """
    checked = (transport.derive_shared_fragment(projected_annotated) if fragment is None else
               transport.validate_shared_fragment(projected_annotated, fragment))
    return Planner(checked).finish()
