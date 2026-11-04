"""Independent, bounded shared rank-1 XMLF *fragment* replay.

This is not an ordinary K checker, an export/3 envelope validator, or a source
lowerer. The compiled producer must still perform real K.check, root/declaration
and source-erasure checks. The complete module envelope must separately replay
module_custody and module_projection. Nothing here changes export/2 or defaults.

The fragment seam implements SOURCE_WIRE_CONTRACT_DRAFT.md f73198a9, sections
3--5, for Int/Bool/arrows and the existing scalar primitives/Int conditional.
One outer with_data can additionally supply referenced, closed, nonrecursive,
parameter-free, single-constructor DATA. Its fields are Int/Bool or closed
arrows recursively over those scalars. Multi-constructor SUM families permit
Int/Bool fields and exact zero-argument self-family atoms, with exhaustive
Int-result cases. The optional self_recursive marker records that extension;
nominal types are never unfolded. Complete shared-use vectors may additionally
contain these exact published nominal atoms or finite closed arrows over them.
Every lowered arrow remains Repeat/unknown. This does not admit nominal atoms in generic code, callable SUM fields, cross-family recursion,
or parameterized/higher-rank data. A separate conditional inventory permits
closed ordinary Int/Bool imports into a top-level direct-lambda generalization.
It establishes lexical types/occurrences only, not runtime provenance or Access.
Exact saturated scalar primitives may occur inside these direct generic lambdas,
with closed scalar dependencies only. Their Instance-only execution still needs
the independent resource checker's raw closed-entry proof; syntax is not authority.
At most one retained recursive group globally
is admitted, containing one concrete closed monomorphic function. Its optional
capture policies permit closed Int/Bool owners, exact full-vector lexical
shared views, and ordinary owners of recursively closed scalar-arrow types.
Already admitted closed DATA/SUM nominal owners have a separate capture policy.
A further explicit policy permits ordinary captured arrows with exact published
nominal leaves; those leaves are type obligations, not additional owners. Open
or higher-rank callables and bare Schemes remain excluded. Its
introduction spine has at most eight exact typed passthrough
wrappers. This is not a termination proof or generic/value-recursion permission.
The complete RHS, including ordinary annotation applications, remains unchanged.

Public results are JSON data, never opaque proof authority. Definition rows omit
resolver_binding; correspondence rows omit original. Those missing fields MUST
be joined to genuine replayed custody/projection before a complete export/3
claim. In particular, an omitted resolver field does not mean a local binder.
The separate fragment schema is named explicitly below, not disguised as /3.
"""
from __future__ import annotations

import json

import module_projection as projection
import transport as fragment

FORMAT = 'mlf-shared-fragment-replay/1'
POLICY = 'shared-rank1-callable/1'
NOMINAL_BETA_POLICY = 'shared-rank1-callable/2'
ARROW_BETA_POLICY = 'shared-rank1-callable/3'
MAX_TYPE_DEPTH = 32  # Existing IR8 logical type bound, not raw JSON depth.
MAX_CELLS = 10_000
MAX_DEPTH = 100
MAX_BYTES = 32 * 1024 * 1024
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_WORK = 2_000_000  # Additional fail-closed implementation work ceiling.
MAX_DEFINITIONS = 16
MAX_PARAMETERS = 8
MAX_USES = 256
MAX_PROOFS = 2048
MAX_PROOF_ATOMS = 64
MAX_ROWS = 10_000
MAX_NOMINALS = 32
MAX_FIELDS = 32
MAX_VARIANTS = 64
MAX_RECURSIVE_WRAPPERS = 8
MAX_RECURSIVE_CAPTURES = 64  # Includes the self owner when it is actually used.
MAX_GENERIC_CAPTURES = 64  # Explicit lexical bindings, even when owners alias.
GENERIC_CAPTURE_POLICY = 'closed-scalar-generalization-captures/1'
SUM_POLICY = 'closed-scalar-sum/1'
SUM_SELF_POLICY = 'closed-self-atom/1'
RECURSION_POLICY = 'closed-single-function-recursion/1'
RECURSIVE_CAPTURE_POLICY = 'closed-scalar-shared-view-captures/1'
RECURSIVE_CALLABLE_CAPTURE_POLICY = 'closed-scalar-callable-shared-view-captures/1'
RECURSIVE_NOMINAL_CAPTURE_POLICY = 'closed-scalar-callable-nominal-shared-view-captures/1'
RECURSIVE_ADMITTED_CALLABLE_CAPTURE_POLICY = 'closed-admitted-callable-shared-view-captures/1'
NOMINAL_POLICY = 'closed-single-constructor-data/1'
INT = {'tag': 'constructor', 'name': 'Int', 'arguments': []}
BOOL = {'tag': 'constructor', 'name': 'Bool', 'arguments': []}


class SharedTransportError(ValueError):
    """A deterministic fragment rejection; never an ordinary compiler verdict."""

    def __init__(self, code, message, path=()):
        self.code = code
        self.path = list(path)
        super().__init__(f'{code} at {list(path)!r}: {message}')


def _fail(code, message, path=()):
    raise SharedTransportError(code, message, path)


def _exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        _fail('SCHEMA', label + ' requires exact keys')


def _same(left, right):
    return projection.exact_equal(left, right)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _bounded(value, *, cells=MAX_CELLS, depth=MAX_DEPTH, byte_limit=MAX_BYTES):
    """Iterative before every recursive boundary, with bounded string chunks."""
    stack = [(False, value, 1)]
    active = set()
    count = used = 0
    while stack:
        leaving, item, level = stack.pop()
        if leaving:
            active.remove(id(item))
            continue
        count += 1
        if count > cells or level > depth:
            _fail('LIMIT', 'JSON cell/depth bound')
        kind = type(item)
        if kind in (dict, list):
            if len(item) * (2 if kind is dict else 1) > cells - count:
                _fail('LIMIT', 'immediate container exceeds remaining JSON cells')
            if id(item) in active:
                _fail('SCHEMA', 'cyclic JSON')
            active.add(id(item))
            stack.append((True, item, level))
            used += 2 + len(item) * (2 if kind is dict else 1)
            if kind is dict:
                # Keys are values for byte/scalar validation, but not AST edges.
                for key, child in item.items():
                    if type(key) is not str:
                        _fail('SCHEMA', 'non-string object key')
                    stack.append((False, key, level + 1))
                    stack.append((False, child, level + 1))
            else:
                stack.extend((False, child, level + 1) for child in item)
        elif kind is str:
            used += 2
            for start in range(0, len(item), 4096):
                try:
                    # JSON escaping is counted, not just unescaped UTF-8.
                    used += len(json.dumps(item[start:start + 4096], ensure_ascii=False).encode('utf-8')) - 2
                except UnicodeError as exc:
                    _fail('SCHEMA', 'non-scalar Unicode: ' + str(exc))
                if used > byte_limit:
                    _fail('LIMIT', 'JSON byte bound')
        elif kind is int:
            if not -(1 << 63) <= item < (1 << 63):
                _fail('SCHEMA', 'integer outside signed64')
            used += len(str(item))
        elif kind is bool or item is None:
            used += 5
        else:
            _fail('SCHEMA', 'non-JSON value')
        if used > byte_limit:
            _fail('LIMIT', 'JSON byte bound')
    return count


class _Budget:
    def __init__(self, *, arrow_arguments=False):
        self.work = 0
        self.metadata = 0
        self.rows = 0
        self.arrow_arguments = arrow_arguments

    def tick(self, count=1):
        self.work += count
        if self.work > MAX_WORK:
            _fail('LIMIT', 'independent replay work bound')

    def record(self, row):
        self.rows += 1
        if self.rows > MAX_ROWS:
            _fail('LIMIT', 'correspondence row bound')
        # Individual data was bounded before construction. Streaming avoids an
        # unbounded aggregate string allocation while charging the final evidence.
        for chunk in json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(',', ':')).iterencode(row):
            for start in range(0, len(chunk), 4096):
                self.metadata += len(chunk[start:start + 4096].encode('utf-8'))
                if self.metadata > MAX_METADATA_BYTES:
                    _fail('LIMIT', 'added correspondence metadata bound')


def _address(stage, path):
    return {'stage': stage, 'path': list(path)}


def _has_arrow_arguments(value):
    """Only enable the additional source guards for a real raw arrow witness.

    The input has already passed the finite JSON guard. This discovery does not
    change old scalar/nominal replay work, rows, or evidence.
    """
    pending = [value]
    while pending:
        node = pending.pop()
        if type(node) is dict:
            if (node.get('tag') == 'bottom' and type(node.get('type')) is dict
                    and node['type'].get('tag') == 'arrow'):
                return True
            pending.extend(node.values())
        elif type(node) is list:
            pending.extend(node)
    return False


def _type_bounds(typ, budget, substitution=None):
    """Preflight logical height and expanded work without expanding a type DAG.

    Optional substitution models the existing capture-avoiding type operation
    before it allocates or any alpha comparison walks its result. Forall is a
    source prefix, not an IR8 type node; each bound/body has its own monotype
    height. Memoization uses object identity plus shadow state, never recursive
    hashing/equality. The local cache and expanded tree weight are both bounded
    by the existing retained-cell limit, with all traversal/work charged.
    """
    memo, active = {}, set()
    pending = [(False, typ, substitution is not None)]
    while pending:
        leaving, node, replace = pending.pop()
        budget.tick()
        key = (id(node), replace)
        if key in memo:
            continue
        if type(node) is not dict:
            _fail('SCHEMA', 'type bound requires a raw type')
        tag = node.get('tag')
        replaced = replace and tag == 'var' and node['id'] == substitution[0]
        if replaced:
            children, adds_depth = [(substitution[1], False)], False
        elif tag == 'arrow':
            children, adds_depth = [(node['from'], replace), (node['to'], replace)], True
        elif tag == 'forall':
            children = [(node['bound'], replace),
                        (node['body'], replace and node['id'] != substitution[0])]
            adds_depth = False
        elif tag == 'constructor':
            children, adds_depth = [(part, replace) for part in node['arguments']], True
        elif tag == 'apply':
            children, adds_depth = [(node['function'], replace), (node['argument'], replace)], True
        elif tag in ('var', 'bottom', 'bottom_kind'):
            children, adds_depth = [], False
        else:
            _fail('SCHEMA', 'unsupported raw type in bound preflight')
        if not leaving:
            if key in active:
                _fail('SCHEMA', 'cyclic raw type')
            if len(memo) + len(active) >= MAX_CELLS:
                _fail('LIMIT', 'type preflight cell bound')
            active.add(key)
            pending.append((True, node, replace))
            pending.extend((False, part, mode) for part, mode in reversed(children))
            continue
        active.remove(key)
        metrics = [memo[(id(part), mode)] for part, mode in children]
        height = max((h for h, _ in metrics), default=0) + int(adds_depth)
        height = max(1, height)
        weight = (0 if replaced else 1) + sum(w for _, w in metrics)
        if height > MAX_TYPE_DEPTH:
            _fail('LIMIT', 'coordinate or substituted logical type depth exceeds 32')
        if weight > MAX_CELLS:
            _fail('LIMIT', 'expanded type exceeds retained-cell work bound')
        memo[key] = (height, weight)
    result = memo[(id(typ), substitution is not None)]
    budget.tick(result[1])  # Reserve the ensuing expanded type walk/copy.
    return result


def _children(node):
    tag = node['tag']
    if tag in ('lambda', 'type_lambda', 'with_data'):
        return [(('body',), node['body'])]
    if tag == 'type_application':
        return [(('value',), node['value'])]
    if tag == 'application':
        return [(('function',), node['function']), (('argument',), node['argument'])]
    if tag == 'let':
        return [(('value',), node['value']), (('body',), node['body'])]
    if tag == 'letrec':
        return [(('bindings', str(i), 'value'), binding['value'])
                for i, binding in enumerate(node['bindings'])] + [(('body',), node['body'])]
    if tag == 'case':
        return [(('scrutinee',), node['scrutinee'])] + [
            (('alternatives', str(i), 'body'), arm['body'])
            for i, arm in enumerate(node['alternatives'])]
    return []


def _walk(root):
    work = [((), root)]
    while work:
        path, node = work.pop()
        yield path, node
        work.extend((path + suffix, child) for suffix, child in reversed(_children(node)))


def _index(key, length):
    if type(key) is not str or not key.isascii() or not key.isdigit() or str(int(key)) != key:
        _fail('SCHEMA', 'noncanonical list path index')
    index = int(key)
    if not 0 <= index < length:
        _fail('SCHEMA', 'list path index out of range')
    return index


def _get(root, path):
    for key in path:
        root = root[_index(key, len(root))] if type(root) is list else root[key]
    return root


def _replace(root, path, value):
    if not path:
        return value
    key = path[0]
    if type(root) is list:
        index = _index(key, len(root))
        changed = list(root)
        changed[index] = _replace(root[index], path[1:], value)
        return changed
    return root | {key: _replace(root[key], path[1:], value)}


def _bottom(typ):
    return typ == {'tag': 'bottom'} or typ == {'tag': 'bottom_kind', 'kind': {'tag': 'star'}}


def _scalar(typ):
    return typ == INT or typ == BOOL


class _Nominals:
    """Exact declaration identities, never a structural-layout equivalence.

    The whole declaration list remains raw evidence. Only referenced rows are
    subjected to the narrower runtime subset, so unrelated compiler dictionary
    declarations are not silently admitted or deleted.
    """

    def __init__(self, root, budget):
        self.budget = budget
        self.declarations = root['declarations'] if root['tag'] == 'with_data' else []
        self.by_name, self.by_constructor, self.selected = {}, {}, {}
        self.self_recursive = set()
        for index, declaration in enumerate(self.declarations):
            budget.tick()
            name = declaration['name']
            if name in self.by_name or name in ('Int', 'Bool'):
                _fail('DECLARATION', 'duplicate or intrinsic nominal declaration', ('declarations', str(index)))
            self.by_name[name] = index
            for constructor in declaration['constructors']:
                budget.tick()
                if constructor['name'] in self.by_constructor:
                    _fail('DECLARATION', 'ambiguous constructor identity', ('declarations', str(index)))
                self.by_constructor[constructor['name']] = index

    def field_type(self, field, path):
        self.budget.tick()
        if field['tag'] == 'applied' and not field['arguments'] and field['name'] in ('Int', 'Bool'):
            return INT if field['name'] == 'Int' else BOOL
        if field['tag'] == 'function':
            return {'tag': 'arrow', 'from': self.field_type(field['from'], path + ('from',)),
                    'to': self.field_type(field['to'], path + ('to',))}
        _fail('NOMINAL', 'DATA fields require only Int/Bool and recursively closed scalar arrows', path)

    def select(self, name, path=()):
        self.budget.tick()
        if name not in self.by_name:
            _fail('TYPE', 'nominal type lacks an exact declaration', path)
        index = self.by_name[name]
        if index in self.selected:
            return self.selected[index]
        if len(self.selected) >= MAX_NOMINALS:
            _fail('LIMIT', 'referenced nominal declaration bound', path)
        declaration = self.declarations[index]
        source = ('declarations', str(index))
        if declaration['parameters'] or not declaration['constructors']:
            _fail('NOMINAL', 'referenced nominal requires no parameters and at least one constructor', source)
        if len(declaration['constructors']) > MAX_VARIANTS:
            _fail('LIMIT', 'SUM variant count exceeds 64', source + ('constructors',))
        if len(declaration['constructors']) > 1:
            variants = []
            self_recursive = False
            for variant_index, constructor in enumerate(declaration['constructors']):
                self.budget.tick()
                cp = source + ('constructors', str(variant_index))
                if len(constructor['fields']) > MAX_FIELDS:
                    _fail('LIMIT', 'SUM field count exceeds 32', cp + ('fields',))
                fields = []
                for field_index, field in enumerate(constructor['fields']):
                    self.budget.tick()
                    if field['tag'] != 'applied' or field['arguments'] or field['name'] not in ('Int', 'Bool', name):
                        _fail('NOMINAL', 'SUM fields require Int/Bool or the exact closed self-family atom',
                              cp + ('fields', str(field_index)))
                    if field['name'] == name:
                        # This is a finite nominal reference, not a request to
                        # select or expand its definition recursively. The raw
                        # declaration/name maps already establish its identity.
                        fields.append({'tag': 'constructor', 'name': name, 'arguments': []})
                        self_recursive = True
                    else:
                        fields.append(INT if field['name'] == 'Int' else BOOL)
                variants.append({'index': variant_index, 'constructor': constructor['name'],
                                 'constructor_source': _address('projected', cp), 'field_types': fields})
            row = {'index': index, 'name': name, 'source': _address('projected', source),
                   'type': {'tag': 'constructor', 'name': name, 'arguments': []}, 'variants': variants}
            self.budget.record(row)
            self.selected[index] = row
            if self_recursive:
                self.self_recursive.add(index)
            return row
        constructor = declaration['constructors'][0]
        if len(constructor['fields']) > MAX_FIELDS:
            _fail('LIMIT', 'DATA field count exceeds 32', source + ('constructors', '0', 'fields'))
        field_types = [self.field_type(field, source + ('constructors', '0', 'fields', str(i)))
                       for i, field in enumerate(constructor['fields'])]
        row = {'index': index, 'name': name, 'source': _address('projected', source),
               'constructor': constructor['name'],
               'constructor_source': _address('projected', source + ('constructors', '0')),
               'field_types': field_types,
               'type': {'tag': 'constructor', 'name': name, 'arguments': []}}
        self.budget.record(row)
        self.selected[index] = row
        return row

    def variant_row(self, owner, constructor, path=()):
        if 'variants' not in owner:
            if constructor != owner['constructor']:
                _fail('CASE', 'constructor is not a member of the exact nominal family', path)
            return owner
        for variant in owner['variants']:
            self.budget.tick()
            if variant['constructor'] == constructor:
                return variant
        _fail('CASE', 'constructor is not a member of the exact nominal family', path)

    def type_row(self, typ, path=()):
        if typ['tag'] != 'constructor' or typ['arguments']:
            _fail('NOMINAL', 'nominal type must be closed and parameter-free', path)
        return self.select(typ['name'], path)

    def constructor_row(self, name, arguments, path=()):
        if name not in self.by_constructor:
            _fail('FRAGMENT', 'constructor lacks an exact declaration', path)
        if arguments:
            _fail('NOMINAL', 'nominal constructor type instantiation is not admitted', path)
        declaration = self.declarations[self.by_constructor[name]]
        return self.select(declaration['name'], path)


def _wf(typ, scope, budget, *, mono=False, nominals=None):
    """Star-kinded types with lexical rigids and exact optional nominal scope."""
    if budget.arrow_arguments:
        _type_bounds(typ, budget)
    return _wf_inner(typ, scope, budget, mono=mono, nominals=nominals)


def _wf_inner(typ, scope, budget, *, mono=False, nominals=None):
    budget.tick()
    tag = typ['tag']
    if tag == 'var':
        if typ['id'] not in scope:
            _fail('TYPE_SCOPE', 'unbound type variable')
    elif tag == 'constructor':
        if not _scalar(typ):
            if nominals is None:
                _fail('TYPE', 'only intrinsic Int/Bool are in this fragment')
            nominals.type_row(typ)
    elif tag == 'arrow':
        _wf_inner(typ['from'], scope, budget, mono=True, nominals=nominals)
        _wf_inner(typ['to'], scope, budget, mono=True, nominals=nominals)
    elif tag == 'forall' and not mono:
        # The binder is NOT in scope over its own bound.
        _wf_inner(typ['bound'], scope, budget, nominals=nominals)
        if typ['id'] in scope:
            _fail('TYPE_SCOPE', 'repeated active type binder')
        _wf_inner(typ['body'], scope | {typ['id']: typ['bound']}, budget, nominals=nominals)
    elif _bottom(typ) and not mono:
        pass
    else:
        _fail('TYPE', 'unsupported kind, bottom term type, or higher-rank type')


def _scope_bindings(bindings, budget):
    if type(bindings) not in (tuple, list):
        _fail('SCHEMA', 'scope must be an ordered sequence')
    result = {}
    for binding in bindings:
        _exact(binding, {'id', 'bound'}, 'scope binding')
        ident = binding['id']
        if type(ident) is not int or not 0 <= ident < (1 << 63) or ident in result:
            _fail('TYPE_SCOPE', 'invalid or duplicate active scope binder')
        fragment.validate_type(binding['bound'])
        _wf(binding['bound'], result, budget)
        result[ident] = binding['bound']
    return result


def _actions(proof, budget):
    atoms = []
    work = [proof]
    while work:
        node = work.pop()
        budget.tick()
        if node['tag'] == 'then':
            work.extend((node['second'], node['first']))
        else:
            atoms.append(node)
            if len(atoms) > MAX_PROOF_ATOMS:
                _fail('LIMIT', 'proof atom bound')
    arguments = []
    pending = None
    for node in atoms:
        if node == {'tag': 'refl'}:
            continue
        if node['tag'] == 'inner' and node['witness']['tag'] == 'bottom' and pending is None:
            pending = node['witness']['type']
        elif node == {'tag': 'elim'} and pending is not None:
            arguments.append(pending)
            pending = None
        else:
            _fail('PROOF', 'only refl and standard inner(bottom(T));elim pairs are admitted')
    if pending is not None:
        _fail('PROOF', 'incomplete elimination pair')
    return arguments


def _compute(proof, source, scope, scope_ref, budget, *, nominals=None):
    _actions(proof, budget)
    rows = []

    def go(p, typ, path):
        budget.tick()
        _wf(typ, scope, budget, nominals=nominals)
        row = {'proof_path': list(path), 'scope': scope_ref,
               'source_type': typ, 'result_type': None}
        rows.append(row)  # Preorder inventory; computation itself is sequential.
        tag = p['tag']
        if tag == 'refl':
            result = typ
        elif tag == 'then':
            middle = go(p['first'], typ, path + ('first',))
            result = go(p['second'], middle, path + ('second',))
        elif tag == 'bottom':
            if not _bottom(typ):
                _fail('PROOF', 'bottom computation requires exact bottom-Star input')
            _wf(p['type'], scope, budget, mono=True, nominals=nominals)
            result = p['type']
        elif tag == 'inner':
            if typ['tag'] != 'forall':
                _fail('PROOF', 'inner computation requires forall input')
            result = typ | {'bound': go(p['witness'], typ['bound'], path + ('witness',))}
        elif tag == 'elim':
            if typ['tag'] != 'forall':
                _fail('PROOF', 'elim computation requires forall input')
            # The admitted scope is fresh through every forall. A well-formed
            # bound cannot contain this or a nested active binder, so this use of
            # existing substitution is capture-avoiding even for raw outer vars.
            if budget.arrow_arguments:
                _type_bounds(typ['body'], budget, (typ['id'], typ['bound']))
            result = fragment.substitute_closed_type(typ['body'], typ['id'], typ['bound'])
            _bounded(result)
        else:
            _fail('PROOF', 'unsupported computation')
        _wf(result, scope, budget, nominals=nominals)
        row['result_type'] = result
        return result

    result = go(proof, source, ())
    return result, rows


def replay_type_computation(witness, source_type, *, scope=()):
    """Replay a raw witness with explicit ordered lexical {id,bound} bindings.

    The output trace is preorder. Its then.second source is the actual result of
    then.first. This public helper permits scoped raw variables, not open shared
    use admission. It is deliberately not a K.check receipt.
    """
    try:
        if type(scope) not in (tuple, list):
            _fail('SCHEMA', 'scope must be an ordered finite sequence')
        if len(scope) > MAX_CELLS:
            _fail('LIMIT', 'scope sequence exceeds retained cell bound')
        _bounded({'witness': witness, 'source_type': source_type, 'scope': list(scope)})
        witness, source_type, bindings = json.loads(_json([witness, source_type, list(scope)]))
        fragment.validate_computation(witness)
        fragment.validate_type(source_type)
        budget = _Budget(arrow_arguments=_has_arrow_arguments(witness))
        env = _scope_bindings(bindings, budget)
        result, rows = _compute(witness, source_type, env, bindings, budget)
        output = {'result_type': result, 'proof_intermediates': rows}
        budget.record(output)
        return output
    except SharedTransportError:
        raise
    except (fragment.BridgeError, projection.ProjectionError, KeyError, TypeError,
            ValueError, RecursionError) as exc:
        _fail('SCHEMA', str(exc))


class _Inference:
    def __init__(self, root, stage, budget, *, scope_start=0, origins=None, nominals=None):
        self.root = root
        self.stage = stage
        self.budget = budget
        self.types = {}
        self.scopes = []
        self.proofs = {}
        self.scope_at = {}
        self.scope_start = scope_start
        self.origins = origins
        self.recursive_paths = []
        self.nominals = _Nominals(root, budget) if nominals is None else nominals
        self.type = self.infer(root, (), {}, {}, None)

    def infer(self, node, path, terms, types, scope_ref):
        self.budget.tick()
        self.scope_at[path] = scope_ref
        tag = node['tag']
        if tag == 'int64':
            typ = INT
        elif tag == 'bool':
            typ = BOOL
        elif tag == 'var':
            if node['name']['id'] not in terms:
                _fail('TERM_SCOPE', 'unbound term variable', path)
            typ = terms[node['name']['id']]
            _wf(typ, types, self.budget, nominals=self.nominals)
        elif tag == 'lambda':
            _wf(node['parameter_type'], types, self.budget, mono=True, nominals=self.nominals)
            body = self.infer(node['body'], path + ('body',),
                              terms | {node['parameter']['id']: node['parameter_type']}, types, scope_ref)
            _wf(body, types, self.budget, mono=True, nominals=self.nominals)
            typ = {'tag': 'arrow', 'from': node['parameter_type'], 'to': body}
        elif tag == 'application':
            fn = self.infer(node['function'], path + ('function',), terms, types, scope_ref)
            arg = self.infer(node['argument'], path + ('argument',), terms, types, scope_ref)
            if fn['tag'] != 'arrow' or not fragment.alpha_type_equal(fn['from'], arg):
                _fail('TYPE', 'ordinary application type mismatch', path)
            typ = fn['to']
        elif tag == 'let':
            value = self.infer(node['value'], path + ('value',), terms, types, scope_ref)
            typ = self.infer(node['body'], path + ('body',),
                             terms | {node['name']['id']: value}, types, scope_ref)
        elif tag == 'letrec':
            if scope_ref is not None or len(node['bindings']) != 1 or self.recursive_paths:
                _fail('RECURSION', 'only one concrete singleton recursive function is admitted', path)
            self.recursive_paths.append(path)
            binding = node['bindings'][0]
            bp = path + ('bindings', '0')
            annotation = binding['type']
            if annotation['tag'] != 'arrow':
                _fail('RECURSION', 'recursive binding requires a closed monomorphic arrow annotation', bp)
            # Deliberately empty type scope: an ambient rigid cannot silently
            # turn a concrete recursive knot into a generic allocation.
            _wf(annotation, {}, self.budget, mono=True, nominals=self.nominals)
            if binding['name']['id'] in terms:
                _fail('TERM_SCOPE', 'recursive binder already in scope', bp)
            inner = terms | {binding['name']['id']: annotation}
            actual = self.infer(binding['value'], bp + ('value',), inner, types, scope_ref)
            if not fragment.alpha_type_equal(actual, annotation):
                _fail('TYPE', 'recursive RHS differs from its complete annotation', bp + ('value',))
            typ = self.infer(node['body'], path + ('body',), inner, types, scope_ref)
        elif tag == 'type_lambda':
            _wf(node['bound'], types, self.budget, nominals=self.nominals)
            if node['id'] in types:
                _fail('TYPE_SCOPE', 'repeated active type abstraction', path)
            if not _bottom(node['bound']):
                _fail('PREFIX', 'only bottom-Star type abstractions are admitted', path)
            ident = self.scope_start + len(self.scopes)
            source = _address(self.stage, path)
            projected = source if self.origins is None else _address('projected', self.origins[path])
            self.scopes.append({'id': ident, 'parent': scope_ref, 'binder': node['id'],
                                'source': source, 'bound': node['bound'], 'projected_source': projected})
            body = self.infer(node['body'], path + ('body',), terms,
                              types | {node['id']: node['bound']}, ident)
            typ = {'tag': 'forall', 'id': node['id'], 'bound': node['bound'], 'body': body}
        elif tag == 'type_application':
            operand = self.infer(node['value'], path + ('value',), terms, types, scope_ref)
            typ, trace = _compute(node['witness'], operand, types, scope_ref, self.budget,
                                  nominals=self.nominals)
            self.proofs[path] = {'input_type': operand, 'proof_intermediates': trace,
                                 'result_type': typ, 'scope': scope_ref}
        elif tag == 'primitive':
            try:
                fragment.primitive_arguments(node, raw=True)
            except fragment.BridgeError as exc:
                _fail('PRIMITIVE', str(exc), path)
            if node['id'] == 13:
                arg = node['arguments'][0]
                _wf(arg, types, self.budget, mono=True, nominals=self.nominals)
                typ = {'tag': 'arrow', 'from': BOOL, 'to': {'tag': 'arrow', 'from': arg,
                       'to': {'tag': 'arrow', 'from': arg, 'to': arg}}}
            else:
                result = BOOL if node['id'] in (10, 11) else INT
                typ = {'tag': 'arrow', 'from': INT, 'to': {'tag': 'arrow', 'from': INT, 'to': result}}
        elif tag == 'constructor':
            row = self.nominals.constructor_row(node['name'], node['arguments'], path)
            typ = row['type']
            variant = self.nominals.variant_row(row, node['name'], path)
            for field in reversed(variant['field_types']):
                typ = {'tag': 'arrow', 'from': field, 'to': typ}
        elif tag == 'case':
            subject = self.infer(node['scrutinee'], path + ('scrutinee',), terms, types, scope_ref)
            if subject['tag'] != 'constructor' or _scalar(subject) or subject['arguments']:
                _fail('CASE', 'case scrutinee must be an exact closed DATA nominal', path)
            owner = self.nominals.type_row(subject, path + ('scrutinee',))
            if 'variants' in owner:
                self.sum_case(node, path, owner, terms, types, scope_ref)
            else:
                if len(node['alternatives']) != 1:
                    _fail('CASE', 'single-constructor DATA requires exactly one matching constructor arm', path)
                alternative = node['alternatives'][0]
                pattern = alternative['pattern']
                pattern_path = path + ('alternatives', '0', 'pattern')
                if pattern['tag'] != 'constructor' or pattern['constructor'] != owner['constructor']:
                    _fail('CASE', 'case pattern must name the exact scrutinee constructor', pattern_path)
                if len(pattern['fields']) != len(owner['field_types']):
                    _fail('CASE', 'case pattern field arity differs', pattern_path)
                bindings = {}
                for binder, field in zip(pattern['fields'], owner['field_types']):
                    self.budget.tick()
                    if binder is not None:
                        if binder['id'] in terms or binder['id'] in bindings:
                            _fail('TERM_SCOPE', 'case pattern repeats an active term binder', pattern_path)
                        bindings[binder['id']] = field
                _wf(node['result_type'], types, self.budget, mono=True, nominals=self.nominals)
                body = self.infer(alternative['body'], path + ('alternatives', '0', 'body'),
                                  terms | bindings, types, scope_ref)
                if not fragment.alpha_type_equal(body, node['result_type']):
                    _fail('TYPE', 'case body differs from its annotated result type', path)
            typ = node['result_type']
        elif tag == 'with_data' and not path:
            typ = self.infer(node['body'], path + ('body',), terms, types, scope_ref)
        else:
            _fail('FRAGMENT', 'unsupported retained term constructor: ' + tag, path)
        if self.budget.arrow_arguments:
            _type_bounds(typ, self.budget)
        self.types[path] = typ
        return typ


    def sum_case(self, node, path, owner, terms, types, scope_ref):
        if not _same(node['result_type'], INT):
            _fail('CASE', 'SUM case result must be exactly Int', path)
        if len(node['alternatives']) != len(owner['variants']):
            _fail('CASE', 'SUM case requires complete constructor coverage', path)
        seen = set()
        for index, alternative in enumerate(node['alternatives']):
            self.budget.tick()
            pattern = alternative['pattern']
            pp = path + ('alternatives', str(index), 'pattern')
            if pattern['tag'] != 'constructor':
                _fail('CASE', 'SUM case requires explicit constructor arms', pp)
            variant = self.nominals.variant_row(owner, pattern['constructor'], pp)
            if variant['index'] in seen:
                _fail('CASE', 'SUM case repeats a constructor arm', pp)
            seen.add(variant['index'])
            if len(pattern['fields']) != len(variant['field_types']):
                _fail('CASE', 'SUM case pattern field arity differs', pp)
            bindings = {}
            for binder, field in zip(pattern['fields'], variant['field_types']):
                self.budget.tick()
                if binder is not None:
                    if binder['id'] in terms or binder['id'] in bindings:
                        _fail('TERM_SCOPE', 'case pattern repeats an active term binder', pp)
                    bindings[binder['id']] = field
            body = self.infer(alternative['body'], path + ('alternatives', str(index), 'body'),
                              terms | bindings, types, scope_ref)
            if not fragment.alpha_type_equal(body, INT):
                _fail('TYPE', 'SUM case body differs from its annotated Int result', path + ('alternatives', str(index), 'body'))
        # Equal count, family membership and distinct indices imply full coverage.



def _spine(node, path):
    wrappers = []
    while node['tag'] == 'type_application':
        wrappers.append((path, node))
        path += ('value',)
        node = node['value']
    return node, path, list(reversed(wrappers))


def _prefix(node, path):
    prefix = []
    while node['tag'] == 'type_lambda':
        prefix.append((path, node))
        path += ('body',)
        node = node['body']
    return node, path, prefix


def _selected_argument(typ, registry, budget, code, path):
    """A closed nominal coordinate must already have passed raw inference.

    No select/type_row call is allowed here: normalization and use inventory
    cannot enlarge the original checked declaration selection.
    """
    budget.tick()
    if (type(typ) is not dict or set(typ) != {'tag', 'name', 'arguments'}
            or typ['tag'] != 'constructor' or typ['arguments']):
        _fail(code, 'complete vector requires intrinsic or admitted closed nominal atoms', path)
    index = registry.by_name.get(typ['name'])
    owner = registry.selected.get(index)
    if owner is None or not _same(owner['type'], typ):
        _fail(code, 'nominal coordinate lacks its already checked declaration', path)
    return owner


def _arrow_argument(typ, registry, budget, code, path):
    """Validate a finite closed arrow and return all nominal-leaf obligations.

    Raw arrows have no ownership-contract fields. Exact raw schema plus the
    unchanged planner lowering supplies Repeat/unknown at every arrow. Never
    select/unfold a family or treat an arrow's leaves as physical captures.
    """
    _type_bounds(typ, budget)
    obligations, pending = [], [(typ, path)]
    while pending:
        node, location = pending.pop()
        budget.tick()
        if _scalar(node):
            continue
        if type(node) is dict and set(node) == {'tag', 'from', 'to'} and node['tag'] == 'arrow':
            pending.extend(((node['to'], location + ('to',)), (node['from'], location + ('from',))))
        else:
            owner = _selected_argument(node, registry, budget, code, location)
            obligations.append((node, owner, location))
    return obligations


def _reconcile_arguments(obligations, registry, published, budget):
    """Bind nominal coordinate obligations to the exact published row objects."""
    for typ, owner, path in obligations:
        budget.tick()
        if _selected_argument(typ, registry, budget, 'USE', path) is not owner:
            _fail('USE', 'nominal coordinate changed declaration identity', path)
        found = False
        for table in published:
            if table is not None:
                for row in table['declarations']:
                    budget.tick()
                    if row is owner:
                        found = True
        if not found:
            _fail('USE', 'nominal coordinate declaration is not published', path)


def _normalize(root, budget, registry):
    current = root
    dialect = POLICY
    origins = {path: path for path, _ in _walk(root)}
    steps = []
    removed = {}
    touched = {}
    while True:
        choice = None
        for path, node in _walk(current):
            budget.tick()
            if node['tag'] != 'type_application':
                continue
            base, base_path, wrappers = _spine(node, path)
            cursor, cursor_path, prefix = _prefix(base, base_path)
            arguments = []
            for _, wrapper in wrappers:
                arguments.extend(_actions(wrapper['witness'], budget))
            if prefix and arguments:
                if len(prefix) > MAX_PARAMETERS or len(arguments) != len(prefix):
                    _fail('DIRECT', 'immediate type spine requires the entire prefix', path)
                if not all(_scalar(arg) for arg in arguments):
                    arrow = False
                    for arg in arguments:
                        if arg['tag'] == 'arrow':
                            _arrow_argument(arg, registry, budget, 'DIRECT', path)
                            arrow = True
                        elif not _scalar(arg):
                            _selected_argument(arg, registry, budget, 'DIRECT', path)
                    if arrow:
                        dialect = ARROW_BETA_POLICY
                    elif dialect != ARROW_BETA_POLICY:
                        dialect = NOMINAL_BETA_POLICY
                after = cursor
                for (_, formal), arg in zip(prefix, arguments):
                    if budget.arrow_arguments:
                        budget.tick(_bounded(after))
                    after = fragment.substitute_closed_term(after, formal['id'], arg)
                    _bounded(after)
                detail = {'rule': 'instantiate_direct_closed',
                          'type_binders': [{'id': n['id'], 'bound': n['bound']} for _, n in prefix],
                          'arguments': arguments, 'witnesses': [n['witness'] for _, n in wrappers],
                          'substitutions': [{'binder': n['id'], 'argument': a} for (_, n), a in zip(prefix, arguments)]}
                choice = (path, node, cursor_path, after, detail)
                break
            if not _actions(node['witness'], budget):
                choice = (path, node, path + ('value',), node['value'],
                          {'rule': 'erase_refl', 'witness': node['witness']})
                break
        if choice is None:
            return current, steps, origins, removed, touched, dialect
        path, before, retained_path, after, detail = choice
        index = len(steps)
        if index >= MAX_PROOFS:
            _fail('LIMIT', 'normalization step bound')
        row = detail | {'input': {'state': index, 'path': list(path), 'subtree': before},
                        'output': {'state': index + 1, 'path': list(path), 'subtree': after}}
        budget.record(row)
        steps.append(row)
        new_origins = {}
        for old_path, original in origins.items():
            budget.tick()
            if old_path[:len(path)] != path:
                new_origins[old_path] = original
                continue
            if _get(root, original)['tag'] == 'type_application':
                touched.setdefault(original, []).append(index)
            if old_path[:len(retained_path)] == retained_path:
                new_origins[path + old_path[len(retained_path):]] = original
            elif _get(root, original)['tag'] == 'type_application':
                removed[original] = 'direct_closed' if detail['rule'] == 'instantiate_direct_closed' else 'refl'
        origins = new_origins
        current = _replace(current, path, after)
        _bounded(current)


def _ordinary(root):
    """Map each actual ordinary syntax occurrence to its exact erased-tree path."""
    rows = []
    work = [((), (), root)]
    while work:
        path, erased, node = work.pop()
        tag = node['tag']
        if tag in ('type_lambda', 'type_application', 'with_data'):
            key = 'value' if tag == 'type_application' else 'body'
            work.append((path + (key,), erased, node[key]))
        else:
            rows.append((path, erased, tag))
            work.extend((path + suffix, erased + suffix, child)
                        for suffix, child in reversed(_children(node)))
    return rows


def _free_terms(root):
    def go(node, bound):
        tag = node['tag']
        if tag == 'var':
            ident = node['name']['id']
            return set() if ident in bound else {ident}
        if tag == 'lambda':
            return go(node['body'], bound | {node['parameter']['id']})
        if tag == 'let':
            return go(node['value'], bound) | go(node['body'], bound | {node['name']['id']})
        if tag == 'letrec':
            inner = bound | {binding['name']['id'] for binding in node['bindings']}
            result = go(node['body'], inner)
            for binding in node['bindings']:
                result |= go(binding['value'], inner)
            return result
        if tag == 'case':
            result = go(node['scrutinee'], bound)
            for arm in node['alternatives']:
                pattern = arm['pattern']
                names = pattern['fields'] if pattern['tag'] == 'constructor' else [pattern['binder']]
                result |= go(arm['body'], bound | {n['id'] for n in names if n is not None})
            return result
        result = set()
        for _, child in _children(node):
            result |= go(child, bound)
        return result
    return go(root, set())


def _nominal_atom(typ, budget):
    work = [typ]
    while work:
        item = work.pop()
        budget.tick()
        if item['tag'] == 'constructor':
            if not _scalar(item):
                return True
        elif item['tag'] == 'arrow':
            work.extend((item['from'], item['to']))
        elif item['tag'] == 'forall':
            work.extend((item['bound'], item['body']))
    return False


def _generic_captures(cursor, cursor_path, free, inferred, schemes, top_level, budget, path):
    """Exact closed scalar imports, never a claim about physical provenance."""
    if not top_level or cursor['tag'] != 'lambda':
        _fail('CAPTURE', 'captured generalization requires a top-level direct lambda', path)
    if len(free) > MAX_GENERIC_CAPTURES:
        _fail('LIMIT', 'generalized scalar imports exceed 64 bindings', path)
    occurrences = {ident: [] for ident in free}
    types = {}
    for suffix, node in _walk(cursor):
        budget.tick()
        if node['tag'] != 'var' or node['name']['id'] not in occurrences:
            continue
        ident = node['name']['id']
        address = cursor_path + suffix
        typ = inferred.types[address]
        if ident in schemes or not _scalar(typ):
            _fail('CAPTURE', 'generic imports require ordinary closed Int/Bool bindings', address)
        if ident in types and not _same(types[ident], typ):
            _fail('CAPTURE', 'generic import occurrence types disagree', address)
        types[ident] = typ
        occurrences[ident].append(_address('normalized', address))
    rows = []
    for ident in free:
        budget.tick()
        if not occurrences[ident]:
            _fail('CAPTURE', 'generic import has no exact free occurrence', path)
        row = {'binding': ident, 'type': types[ident], 'occurrences': occurrences[ident]}
        budget.record(row)
        rows.append(row)
    return {'policy': GENERIC_CAPTURE_POLICY, 'scalars': rows}


def _generic_primitive(root, head, path, context, inferred, budget):
    """Validate a complete original spine, without reducing or moving its work."""
    definition, top_level = context
    cursor_path = tuple(definition['rhs_cursor']['path'])
    budget.tick(1 + len(cursor_path))
    if not top_level or _get(root, cursor_path)['tag'] != 'lambda':
        _fail('FRAGMENT', 'generic scalar computation requires a top-level direct lambda', path)
    current, arguments = path, []
    while current and current[-1] == 'function':
        parent_path = current[:-1]
        budget.tick(1 + len(parent_path))
        parent = _get(root, parent_path)
        if parent['tag'] != 'application':
            break
        arguments.append(parent_path + ('argument',))
        current = parent_path
    conditional = head['id'] == 13
    expected = (BOOL, INT, INT) if conditional else (INT, INT)
    if len(arguments) != len(expected):
        _fail('PRIMITIVE', 'generic primitive requires its complete direct application spine', path)
    if conditional and head['arguments'] != [INT]:
        _fail('PRIMITIVE', 'retained conditional must be instantiated at Int', path)
    for argument_path, typ in zip(arguments, expected):
        budget.tick()
        if not _same(inferred.types[argument_path], typ):
            _fail('PRIMITIVE', 'generic primitive requires exact closed scalar operands', argument_path)
    budget.tick(1 + len(current))
    computation = _get(root, current)
    # Precharge the bounded syntax traversal before the existing lexical helper.
    for _ in _walk(computation):
        budget.tick()
    free = _free_terms(computation)
    for suffix, node in _walk(computation):
        budget.tick()
        if node['tag'] == 'var' and node['name']['id'] in free:
            occurrence = current + suffix
            if not _scalar(inferred.types[occurrence]):
                _fail('CAPTURE', 'generic scalar computation dependencies must be closed Int/Bool', occurrence)


def _inventory(original, normalized, original_infer, normalized_infer, origins, removed, touched, budget, obligations, dialect):
    original_paths = [p for p, n in _walk(original) if n['tag'] == 'type_application']
    if len(original_paths) > MAX_PROOFS:
        _fail('LIMIT', 'type-application evidence bound')
    proof_ids = {p: i for i, p in enumerate(original_paths)}
    normalized_paths = {origin: path for path, origin in origins.items()}
    term_ids = {path: i for i, (path, _) in enumerate(_walk(normalized))}
    definitions = []
    uses = []
    used_proofs = set()
    use_counts = {}

    def go(node, path, schemes, generic=False, top_level=True):
        budget.tick()
        tag = node['tag']
        if generic and _nominal_atom(normalized_infer.types[path], budget):
            _fail('NOMINAL_SCOPE', 'retained generic scope cannot contain nominal DATA atoms', path)
        if tag == 'let':
            value_path = path + ('value',)
            cursor, cursor_path, prefix = _prefix(node['value'], value_path)
            if prefix:
                if generic:
                    _fail('NESTED', 'nested generalization is not admitted', path)
                if len(definitions) >= MAX_DEFINITIONS or len(prefix) > MAX_PARAMETERS:
                    _fail('LIMIT', 'definition/formal bound', path)
                free = sorted(_free_terms(node['value']))
                captures = (_generic_captures(cursor, cursor_path, free, normalized_infer,
                            schemes, top_level, budget, path) if free else None)
                typ = normalized_infer.types[value_path]
                body_type = normalized_infer.types[cursor_path]
                if body_type['tag'] != 'arrow':
                    _fail('SCHEME', 'generalized RHS must have a monomorphic arrow body', path)
                if _nominal_atom(body_type, budget):
                    _fail('NOMINAL_SCOPE', 'Scheme body cannot contain nominal DATA atoms', path)
                ident = len(definitions)
                row = {'id': ident, 'binding': node['name'],
                       'binding_source': _address('normalized', path),
                       'prefix': [{'source': _address('normalized', p), 'id': n['id'],
                                   'bound': n['bound'], 'rigid_index': i}
                                  for i, (p, n) in enumerate(prefix)],
                       'scheme_type': typ, 'body_type': body_type,
                       'rhs': _address('normalized', value_path),
                       'rhs_cursor': _address('normalized', cursor_path),
                       'ordinary_nodes': [term_ids[p] for p, _, _ in _ordinary(node['value'])
                                          for p in [value_path + p]],
                       'free_term_bindings': free}
                if captures is not None:
                    row['captures'] = captures
                budget.record(row)
                definitions.append(row)
                use_counts[ident] = 0
                go(cursor, cursor_path, {}, (row, top_level), False)
                go(node['body'], path + ('body',), schemes | {node['name']['id']: row}, generic, top_level)
            else:
                if normalized_infer.types[value_path]['tag'] == 'forall':
                    _fail('SCHEME', 'a Scheme alias is not a generalization', value_path)
                go(node['value'], value_path, schemes, generic, False)
                go(node['body'], path + ('body',), schemes, generic, top_level)
            return
        if tag == 'type_application':
            base, base_path, wrappers = _spine(node, path)
            if base['tag'] != 'var' or base['name']['id'] not in schemes:
                _fail('PROOF', 'surviving type application is not an exact shared use', path)
            definition = schemes[base['name']['id']]
            arguments = []
            for wrapper_path, wrapper in wrappers:
                arguments.extend(_actions(wrapper['witness'], budget))
                used_proofs.add(origins[wrapper_path])
            if len(arguments) != len(definition['prefix']):
                _fail('USE', 'bare, partial, or extra Scheme elimination', path)
            if not all(_scalar(arg) for arg in arguments):
                for arg in arguments:
                    if arg['tag'] == 'arrow':
                        obligations.extend(_arrow_argument(arg, original_infer.nominals, budget, 'USE', path))
                    elif not _scalar(arg):
                        owner = _selected_argument(arg, original_infer.nominals, budget, 'USE', path)
                        budget.tick()
                        obligations.append((arg, owner, path))
            expected = definition['body_type']
            for formal, argument in zip(definition['prefix'], arguments):
                if budget.arrow_arguments:
                    _type_bounds(expected, budget, (formal['id'], argument))
                expected = fragment.substitute_closed_type(expected, formal['id'], argument)
            actual = normalized_infer.types[path]
            if not fragment.alpha_type_equal(actual, expected):
                _fail('USE', 'full-vector instantiated type mismatch', path)
            use_counts[definition['id']] += 1
            if use_counts[definition['id']] > MAX_USES:
                _fail('LIMIT', 'use-spine bound', path)
            # Recover the complete original proof spine from the surviving
            # variable occurrence, including refl wrappers erased by replay.
            # Proof inventory IDs always refer to projected syntax occurrences.
            original_spine = []
            original_path = origins[base_path]
            while original_path and original_path[-1] == 'value':
                parent_path = original_path[:-1]
                parent = _get(original, parent_path)
                if parent['tag'] != 'type_application':
                    break
                original_spine.append(proof_ids[parent_path])
                original_path = parent_path
            row = {'id': len(uses), 'definition': definition['id'],
                   'source': _address('normalized', path), 'variable': _address('normalized', base_path),
                   'type_applications': original_spine,
                   'arguments': arguments, 'instantiated_type': actual}
            budget.record(row)
            uses.append(row)
            return
        if tag == 'var' and node['name']['id'] in schemes:
            _fail('USE', 'bare or escaping Scheme occurrence', path)
        if tag == 'type_lambda':
            _fail('SCHEME', 'type abstraction outside a supported let prefix', path)
        if generic and tag == 'primitive':
            _generic_primitive(normalized, node, path, generic, normalized_infer, budget)
        elif generic and tag not in ('var', 'lambda', 'application', 'let', 'int64', 'bool'):
            _fail('FRAGMENT', 'generic construction opcode outside exact allowlist', path)
        if tag == 'primitive' and node['id'] == 13 and node['arguments'] != [INT]:
            _fail('PRIMITIVE', 'retained conditional must be instantiated at Int', path)
        for suffix, child in _children(node):
            go(child, path + suffix, schemes, generic, top_level and tag == 'with_data')

    go(normalized, (), {})
    proofs = []
    for path in original_paths:
        node = _get(original, path)
        row = {'id': proof_ids[path], 'source': _address('projected', path),
               'normalized_source': _address('normalized', normalized_paths[path]) if path in normalized_paths else None,
               'operand': _address('projected', path + ('value',)), 'witness': node['witness'],
               **original_infer.proofs[path], 'normalization_steps': touched.get(path, []),
               'disposition': removed.get(path, 'shared_use' if path in used_proofs else None)}
        if row['disposition'] is None:
            _fail('PROOF', 'unclassified retained proof occurrence', path)
        budget.record(row)
        proofs.append(row)
    scopes = original_infer.scopes + normalized_infer.scopes
    for row in scopes:
        budget.record(row)
    return {'policy': dialect, 'definitions': definitions, 'type_scopes': scopes,
            'type_applications': proofs, 'uses': uses}


def _nominal_inventory(root, inferred, registry, budget):
    """Associate exact normalized occurrences without reducing ordinary terms."""
    constructors, cases, sum_constructors, sum_cases, consumed = [], [], [], [], set()
    for path, node in _walk(root):
        budget.tick()
        tag = node['tag']
        if tag in ('application', 'constructor') and path not in consumed:
            head, head_path, arguments, applications = node, path, [], []
            while head['tag'] == 'application':
                budget.tick()
                applications.append(head_path)
                arguments.append((head_path + ('argument',), head['argument']))
                head_path += ('function',)
                head = head['function']
            if head['tag'] == 'constructor':
                owner = registry.constructor_row(head['name'], head['arguments'], head_path)
                variant = registry.variant_row(owner, head['name'], head_path)
                arguments.reverse()
                applications.reverse()
                if len(arguments) != len(variant['field_types']):
                    _fail('CONSTRUCTOR', 'DATA constructor requires its complete field application spine', path)
                for (argument_path, _), field_type in zip(arguments, variant['field_types']):
                    budget.tick()
                    if not fragment.alpha_type_equal(inferred.types[argument_path], field_type):
                        _fail('TYPE', 'DATA constructor field type differs', argument_path)
                if not fragment.alpha_type_equal(inferred.types[path], owner['type']):
                    _fail('TYPE', 'DATA constructor result differs from its nominal owner', path)
                consumed.update(applications)
                consumed.add(head_path)
                row = {'source': _address('normalized', path), 'head': _address('normalized', head_path),
                       'declaration': owner['index'],
                       'arguments': [_address('normalized', p) for p, _ in arguments],
                       'application_spine': [_address('normalized', p) for p in applications],
                       'result_type': owner['type']}
                if 'variants' in owner:
                    row['variant'] = variant['index']
                budget.record(row)
                (sum_constructors if 'variants' in owner else constructors).append(row)
        if tag == 'case':
            owner = registry.type_row(inferred.types[path + ('scrutinee',)], path)
            if 'variants' in owner:
                arms = []
                for index, alternative in enumerate(node['alternatives']):
                    budget.tick()
                    pattern = alternative['pattern']
                    variant = registry.variant_row(owner, pattern['constructor'], path)
                    ap = path + ('alternatives', str(index))
                    arms.append({'index': index, 'variant': variant['index'],
                                 'constructor': variant['constructor'],
                                 'pattern_source': _address('normalized', ap + ('pattern',)),
                                 'fields': [{'index': i, 'binding': binder, 'type': typ}
                                            for i, (binder, typ) in enumerate(zip(pattern['fields'], variant['field_types']))],
                                 'body': _address('normalized', ap + ('body',))})
                row = {'source': _address('normalized', path), 'declaration': owner['index'],
                       'scrutinee': _address('normalized', path + ('scrutinee',)),
                       'result_type': node['result_type'], 'arms': arms}
                budget.record(row)
                sum_cases.append(row)
                continue
            pattern = node['alternatives'][0]['pattern']
            row = {'source': _address('normalized', path), 'declaration': owner['index'],
                   'scrutinee': _address('normalized', path + ('scrutinee',)),
                   'constructor': owner['constructor'],
                   'pattern_source': _address('normalized', path + ('alternatives', '0', 'pattern')),
                   'fields': [{'index': i, 'binding': binder, 'type': typ}
                              for i, (binder, typ) in enumerate(zip(pattern['fields'], owner['field_types']))],
                   'body': _address('normalized', path + ('alternatives', '0', 'body')),
                   'result_type': node['result_type']}
            budget.record(row)
            cases.append(row)
    data_rows, sum_rows = [], []
    for index in sorted(registry.selected):
        row = registry.selected[index]
        (sum_rows if 'variants' in row else data_rows).append(row)
    data = ({'policy': NOMINAL_POLICY, 'declarations': data_rows,
             'constructors': constructors, 'cases': cases} if data_rows else None)
    sums = ({'policy': SUM_POLICY, 'declarations': sum_rows,
             'constructors': sum_constructors, 'cases': sum_cases} if sum_rows else None)
    if registry.self_recursive:
        marker = {'policy': SUM_SELF_POLICY, 'declarations': sorted(registry.self_recursive)}
        budget.record(marker)
        sums['self_recursive'] = marker
    return data, sums


def _closed_scalar_callable(typ, budget):
    """A root arrow with only exact Int/Bool leaves, not a Code/origin proof.

    Raw input is already snapshotted and depth/cell bounded. Charge each node
    of this iterative check; do not recursively expand aliases or nominals.
    """
    if type(typ) is not dict or typ.get('tag') != 'arrow':
        return False
    work = [typ]
    while work:
        budget.tick()
        node = work.pop()
        if _scalar(node):
            continue
        if type(node) is not dict or set(node) != {'tag', 'from', 'to'} or node['tag'] != 'arrow':
            return False
        work.extend((node['from'], node['to']))
    return True


def _published_nominal_capture(typ, path, registry, published, budget):
    """Use an admitted canonical declaration, never select a new family here.

    _nominal_inventory publishes the freshly checked registry rows themselves.
    Their local identity proves the entire declaration is already represented;
    neither caller-supplied evidence nor equal-looking field shapes are used.
    """
    index = registry.by_name.get(typ['name'])
    if index not in registry.selected:
        _fail('RECURSION', 'nominal capture lacks an already admitted declaration', path)
    owner = registry.type_row(typ, path)
    for table in published:
        if table is None:
            continue
        for row in table['declarations']:
            budget.tick()
            if row is owner:
                return owner['index']
    _fail('RECURSION', 'nominal capture declaration is absent from published DATA/SUM evidence', path)


def _closed_admitted_callable(typ, path, registry, published, budget):
    """An exact root arrow with at least one already published nominal leaf.

    Called only after the unchanged scalar-arrow check. The snapshotted type
    has existing depth/cell bounds; charge every visited node and declaration
    lookup. Never select a new family, unfold a nominal, or infer a target Code,
    origin, readiness, support relation or extra physical capture from its type.
    """
    if type(typ) is not dict or typ.get('tag') != 'arrow':
        return False
    work, nominal = [typ], False
    while work:
        budget.tick()
        node = work.pop()
        if _scalar(node):
            continue
        if type(node) is not dict:
            return False
        if set(node) == {'tag', 'from', 'to'} and node['tag'] == 'arrow':
            work.extend((node['to'], node['from']))
        elif (set(node) == {'tag', 'name', 'arguments'} and node['tag'] == 'constructor'
              and type(node['name']) is str and node['arguments'] == []):
            _published_nominal_capture(node, path, registry, published, budget)
            nominal = True
        else:
            return False
    return nominal


def _view_argument_key(typ, registry, budget, path):
    """Full closed logical identity/order for the new saved-arrow-view branch.

    Caller preflights depth and expanded weight before tuple construction and
    hashing. Nominal identity is the already selected declaration, not layout
    equality; the order agrees with the planner's complete logical tuples.
    """
    budget.tick()
    if _scalar(typ):
        return ('scalar', '#i64' if typ == INT else '#bool')
    if typ['tag'] == 'arrow':
        return ('arrow', _view_argument_key(typ['from'], registry, budget, path),
                _view_argument_key(typ['to'], registry, budget, path), 'repeat', 'unknown')
    owner = _selected_argument(typ, registry, budget, 'RECURSION', path)
    return ('nominal', owner['index'], owner['name'], tuple(owner['source']['path']))


def _recursive_captures(rhs, rhs_path, free, self_uses, inferred, inventory, published, budget):
    """Partition all external raw variables using checked lexical use evidence.

    A Scheme's raw free binder ID is not a physical capture. Each occurrence
    must be the base of an already replayed, complete shared-use spine; its key
    retains the actual definition binder and EVERY ordered argument, including
    unused coordinates. This data conveys no origin/Access or E0 inference.
    """
    free = set(free)
    definitions = {row['id']: row for row in inventory['definitions']}
    uses = {}
    for use in inventory['uses']:
        budget.tick()
        path = tuple(use['variable']['path'])
        definition = definitions[use['definition']]
        if (path[:len(rhs_path)] == rhs_path and definition['binding']['id'] in free):
            if path in uses:
                _fail('RECURSION', 'shared view occurrence is not unique', path)
            uses[path] = use
    structural_views = any(typ['tag'] == 'arrow' for use in uses.values() for typ in use['arguments'])
    max_view_weight = 1
    scalars, callables, nominals, views, accounted = {}, {}, {}, {}, set()
    admitted_callable = False
    for relative, node in _walk(rhs):
        budget.tick()
        if node['tag'] != 'var' or node['name']['id'] not in free:
            continue
        path = rhs_path + relative
        ident, typ = node['name']['id'], inferred.types[path]
        accounted.add(ident)
        if _scalar(typ):
            row = scalars.setdefault(ident, {'binding': node['name'], 'type': typ, 'occurrences': []})
            if not _same(row['type'], typ):
                _fail('RECURSION', 'scalar capture has inconsistent lexical types', path)
            row['occurrences'].append(_address('normalized', path))
        elif _closed_scalar_callable(typ, budget):
            # This is the lexical ordinary owner, possibly still pending. Its
            # eventual target/Code/Access cannot be deduced from an arrow type.
            row = callables.setdefault(ident, {'binding': node['name'], 'type': typ, 'occurrences': []})
            if not _same(row['type'], typ):
                _fail('RECURSION', 'callable capture has inconsistent complete lexical types', path)
            row['occurrences'].append(_address('normalized', path))
        elif (typ['tag'] == 'arrow' and
              _closed_admitted_callable(typ, path, inferred.nominals, published, budget)):
            # The owner remains an ordinary pending-capable callable. Nominal
            # leaves are checked against published declarations, not captured.
            admitted_callable = True
            row = callables.setdefault(ident, {'binding': node['name'], 'type': typ, 'occurrences': []})
            if not _same(row['type'], typ):
                _fail('RECURSION', 'callable capture has inconsistent complete lexical types', path)
            row['occurrences'].append(_address('normalized', path))
        elif typ['tag'] == 'constructor' and not typ['arguments']:
            declaration = _published_nominal_capture(typ, path, inferred.nominals, published, budget)
            row = nominals.setdefault(ident, {'binding': node['name'], 'type': typ,
                                             'declaration': declaration, 'occurrences': []})
            if row['declaration'] != declaration or not _same(row['type'], typ):
                _fail('RECURSION', 'nominal capture has inconsistent exact declaration/type', path)
            row['occurrences'].append(_address('normalized', path))
        else:
            use = uses.pop(path, None)
            if use is None:
                _fail('RECURSION', 'external capture lacks an admitted ordinary type or exact shared view', path)
            definition = definitions[use['definition']]
            if definition['binding']['id'] != ident:
                _fail('RECURSION', 'shared capture binder differs from its lexical definition', path)
            if structural_views:
                weight = sum(_type_bounds(t, budget)[1] for t in use['arguments'])
                budget.tick(weight * 2)  # Tuple hashing and full-vector matching.
                max_view_weight = max(max_view_weight, weight)
                key = (ident, tuple(_view_argument_key(t, inferred.nominals, budget, path)
                                    for t in use['arguments']))
            else:
                key = (ident, tuple(t['name'] for t in use['arguments']))
            row = views.setdefault(key, {'definition': use['definition'], 'binding': definition['binding'],
                'arguments': use['arguments'], 'instantiated_type': use['instantiated_type'], 'uses': []})
            if (row['definition'] != use['definition'] or not _same(row['arguments'], use['arguments'])
                    or not _same(row['instantiated_type'], use['instantiated_type'])):
                _fail('RECURSION', 'shared capture full-vector type differs', path)
            row['uses'].append(use['id'])
        if len(scalars) + len(callables) + len(nominals) + len(views) + bool(self_uses) > MAX_RECURSIVE_CAPTURES:
            _fail('LIMIT', 'recursive carrier exceeds 64 captures including self', path)
    if accounted != free or uses:
        _fail('RECURSION', 'recursive free-term inventory is not completely classified', rhs_path)
    if structural_views:
        # At most64 keys. Reserve even an all-pairs comparison bound rather than
        # allow recursive tuple sorting to do uncharged expanded type work.
        budget.tick(len(views) * len(views) * max_view_weight)
    result = {'policy': RECURSIVE_CAPTURE_POLICY,
              'scalars': [scalars[key] for key in sorted(scalars)],
              'views': [views[key] for key in sorted(views)]}
    # No new key or policy for existing scalar/shared-only or capture-free code.
    if callables or nominals:
        result['policy'] = RECURSIVE_NOMINAL_CAPTURE_POLICY if nominals else RECURSIVE_CALLABLE_CAPTURE_POLICY
        result['callables'] = [callables[key] for key in sorted(callables)]
    if nominals:
        result['nominals'] = [nominals[key] for key in sorted(nominals)]
    if admitted_callable:
        result['policy'] = RECURSIVE_ADMITTED_CALLABLE_CAPTURE_POLICY
        result['nominals'] = [nominals[key] for key in sorted(nominals)]
    return result


def _recursion_inventory(root, inferred, inventory, published, budget):
    """Return admission evidence only; NEVER a replacement term or RHS.

    A concrete function introduction may have the compiler's ordinary typed
    annotation applications around it. Each permitted wrapper is an exact
    syntactic, capture-free passthrough at the checked annotation. This narrow
    eligibility test does not beta-reduce, skip evaluation, or recognize names.
    The planner must emit the full RHS and fill its knot with that pending root.
    """
    if not inferred.recursive_paths:
        return None
    path, = inferred.recursive_paths
    node = _get(root, path)
    binding = node['bindings'][0]
    bp = path + ('bindings', '0')
    rhs_path = bp + ('value',)
    annotation, ident = binding['type'], binding['name']['id']
    rhs = binding['value']
    free = sorted(_free_terms(rhs) - {ident})
    cursor, cursor_path, wrappers = rhs, rhs_path, []
    while cursor['tag'] == 'application':
        budget.tick()
        if len(wrappers) >= MAX_RECURSIVE_WRAPPERS:
            _fail('LIMIT', 'recursive function wrapper spine exceeds eight applications', cursor_path)
        fn, fp = cursor['function'], cursor_path + ('function',)
        if (fn['tag'] != 'lambda' or not _same(fn['parameter_type'], annotation)
                or fn['body']['tag'] != 'var'
                or fn['body']['name']['id'] != fn['parameter']['id']
                or _free_terms(fn)
                or not _same(inferred.types[fp], {'tag': 'arrow', 'from': annotation, 'to': annotation})):
            _fail('RECURSION', 'recursive RHS wrapper is not an exact closed typed passthrough', fp)
        wrappers.append({'application': _address('normalized', cursor_path),
                         'function': _address('normalized', fp), 'parameter': fn['parameter']})
        cursor, cursor_path = cursor['argument'], cursor_path + ('argument',)
    if (cursor['tag'] != 'lambda' or not _same(cursor['parameter_type'], annotation['from'])
            or not _same(inferred.types[cursor_path], annotation)):
        _fail('RECURSION', 'recursive RHS must introduce the exactly annotated function', cursor_path)
    self_uses = []
    guarded = cursor_path + ('body',)
    for relative, term in _walk(rhs):
        budget.tick()
        if term['tag'] == 'var' and term['name']['id'] == ident:
            occurrence = rhs_path + relative
            if occurrence[:len(guarded)] != guarded:
                _fail('RECURSION', 'recursive self use is outside the introduced function body', occurrence)
            self_uses.append(_address('normalized', occurrence))
    row = {'source': _address('normalized', path), 'binding_source': _address('normalized', bp),
           'binding': binding['name'], 'type': annotation, 'rhs': _address('normalized', rhs_path),
           'body': _address('normalized', path + ('body',)),
           'function_source': _address('normalized', cursor_path), 'wrappers': wrappers,
           'self_uses': self_uses, 'free_term_bindings': free}
    if free:
        row['captures'] = _recursive_captures(rhs, rhs_path, free, self_uses, inferred, inventory, published, budget)
    result = {'policy': RECURSION_POLICY, 'bindings': [row]}
    budget.record(result)
    return result


def derive_shared_fragment(projected_annotated):
    """Derive independently replayed fragment evidence without source authority.

    Input is the *already projected*, complete raw retained XMLF vocabulary, not
    the old closed executable AST. The two deliberately missing custody joins
    (original addresses, resolver_binding) are described in the module docstring.
    Caller data is snapshotted; returned data never aliases caller-owned inputs.
    """
    try:
        _bounded(projected_annotated)
        root = json.loads(_json(projected_annotated))
        projection.validate_raw_term(root, require_closed=True)
        budget = _Budget(arrow_arguments=_has_arrow_arguments(root))
        nominals = _Nominals(root, budget)
        raw = _Inference(root, 'projected', budget, nominals=nominals)
        normal, steps, origins, removed, touched, dialect = _normalize(root, budget, nominals)
        projection.validate_raw_term(normal, require_closed=True)
        normalized = _Inference(normal, 'normalized', budget, scope_start=len(raw.scopes),
                                origins=origins, nominals=nominals)
        if not fragment.alpha_type_equal(raw.type, normalized.type):
            _fail('TYPE', 'normalization changed replayed root type')
        _wf(normalized.type, {}, budget, mono=True, nominals=nominals)
        before_erased = projection.erase_total(root)
        after_erased = projection.erase_total(normal)
        if not _same(before_erased, after_erased):
            _fail('GRAPH', 'normalization changed ordinary erasure')
        left = _ordinary(root)
        right = _ordinary(normal)
        if len(left) != len(right):
            _fail('GRAPH', 'ordinary node count changed')
        correspondence = []
        for (p, erased, tag), (q, other_erased, other_tag) in zip(left, right):
            if erased != other_erased or tag != other_tag or origins[q] != p:
                _fail('GRAPH', 'ordinary node identity/edge changed')
            row = {'projected': _address('projected', p), 'normalized': _address('normalized', q),
                   'erased_path': list(erased), 'tag': tag}
            budget.record(row)
            correspondence.append(row)
        obligations = []
        inventory = _inventory(root, normal, raw, normalized, origins, removed, touched, budget, obligations, dialect)
        nominal_inventory, sum_inventory = _nominal_inventory(normal, normalized, nominals, budget)
        _reconcile_arguments(obligations, nominals, (nominal_inventory, sum_inventory), budget)
        recursion_inventory = _recursion_inventory(normal, normalized, inventory,
                                                   (nominal_inventory, sum_inventory), budget)
        result = {'format': FORMAT, 'status': 'independent-fragment-replay-only', 'policy': dialect,
                  'input_checked_type': raw.type, 'checked_type': normalized.type,
                  'input_annotated': root, 'input_erased': before_erased,
                  'raw_normalized': normal, 'steps': steps, 'term_correspondence': correspondence,
                  'polymorphism': inventory}
        if nominal_inventory is not None:
            result['nominal_data'] = nominal_inventory
        if sum_inventory is not None:
            result['nominal_sum'] = sum_inventory
        if recursion_inventory is not None:
            result['recursion'] = recursion_inventory
        _bounded(result, cells=500_000, depth=MAX_DEPTH + 20, byte_limit=MAX_BYTES)
        return result
    except SharedTransportError:
        raise
    except (fragment.BridgeError, projection.ProjectionError, KeyError, TypeError,
            ValueError, RecursionError) as exc:
        _fail('SCHEMA', str(exc))


def validate_shared_fragment(projected_annotated, claimed):
    """Recompute every field and reject forged/missing/extra evidence.

    The returned evidence remains fragment replay only. No producer guard boolean
    can upgrade this API into a genuine compiled CheckedTerm or source admission.
    """
    _bounded(claimed, cells=500_000, depth=MAX_DEPTH + 20, byte_limit=MAX_BYTES)
    expected = derive_shared_fragment(projected_annotated)
    if not _same(expected, claimed):
        _fail('EVIDENCE', 'claimed fragment evidence differs from independent replay')
    return expected
