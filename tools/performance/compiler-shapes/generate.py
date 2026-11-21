"""Deterministic, identical shared-Haskell programs with independent IO oracles."""
from pathlib import Path
import hashlib
import json

import data_shapes
import rank_shapes

REGISTRY = json.loads(Path(__file__).with_name('matrix.json').read_text())
HEADER = '''-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main (main) where {
import MLF.Primitive;
'''
MAIN = r'''
main :: IO ();
main = ioBind (getArg 0) (\text -> printInt (entry (readInt text)))
}
'''
FAMILIES = tuple(name for name in REGISTRY['families'] if name != 'baseline')


def balanced(expressions, combine):
    if len(expressions) == 1:
        return expressions[0]
    half = len(expressions) // 2
    return combine(balanced(expressions[:half], combine), balanced(expressions[half:], combine))


def tag_selector(lo, hi):
    """Pick a tag with logarithmic expression depth; bounds are inclusive."""
    if lo == hi:
        return f'Tag{lo}'
    mid = (lo + hi + 1) // 2
    return f'if ltInt x {mid} then ({tag_selector(lo, mid-1)}) else ({tag_selector(mid, hi)})'


def program(family, n):
    """No generated declaration is intentionally unreachable from the IO entry."""
    if family == 'baseline':
        declarations, expression = '', 'x'
    elif family in ('flat_functions', 'inferred_functions', 'local_functions', 'dependency_chain', 'inferred_chain'):
        declarations = ''
        for i in range(n):
            if family not in ('inferred_chain', 'inferred_functions'):
                declarations += f'f{i} :: Int -> Int;\n'
            rhs = f'addInt x {i}' if family in ('flat_functions','inferred_functions','local_functions') else ('addInt x 1' if i == 0 else f'f{i-1} (addInt x 1)')
            declarations += f'f{i} x = {rhs};\n'
        expression = (balanced([f'f{i} x' for i in range(n)], lambda a,b:f'addInt ({a}) ({b})')
                      if family in ('flat_functions','inferred_functions','local_functions') else f'f{n-1} x')
        if family == 'local_functions':
            expression = 'let {\n'+declarations+'} in '+expression
            declarations = ''
    elif family == 'inferred_poly_chain':
        declarations = 'f0 step y = step y;\n'
        declarations += ''.join(f'f{i} step y = step (f{i-1} step y);\n' for i in range(1, n))
        integer = f'f{n-1} (\\value -> addInt value 1) x'
        boolean = f'f{n-1} (\\value -> if value then False else True) (ltInt x 0)'
        expression = f'if {boolean} then {integer} else subInt 0 ({integer})'
    elif family == 'inferred_poly_functions':
        bodies = ('y = y', 'y z = y', 'f y = f y', 'f g y = f (g y)')
        declarations = ''.join(f'f{i} {bodies[i % 4]};\n' for i in range(n))
        terms = []
        for i in range(n):
            integer, boolean = f'(addInt x {i})', f'(ltInt x {i})'
            def call(value, ignored):
                args = (value, f'{value} {ignored}', f'(\\v -> v) {value}',
                        f'(\\v -> v) (\\v -> v) {value}')[i % 4]
                return f'f{i} {args}'
            integer_call = call(integer, boolean)
            terms.append(f'if {call(boolean, integer)} then {integer_call} else subInt 0 ({integer_call})')
        expression = balanced(terms, lambda a,b:f'addInt ({a}) ({b})')
    elif family == 'recursive_ring':
        declarations = ''.join(f'f{i} :: Int -> Int;\nf{i} x = if ltInt x 1 then {i} else f{(i+1)%n} (subInt x 1);\n' for i in range(n))
        expression = 'f0 x'
    elif family in ('mono_calls', 'poly_calls'):
        ty = 'Int' if family == 'mono_calls' else 'a'
        quantified = 'forall a. ' if family == 'poly_calls' else ''
        declarations = f'data Box a = Box a;\nhold :: {quantified}{ty} -> Box {ty};\nhold y = Box y;\nunbox :: {quantified}Box {ty} -> {ty};\nunbox b = case b of {{ Box y -> y }};\n'
        expression = balanced([f'unbox (hold (addInt x {i}))' for i in range(n)], lambda a,b:f'addInt ({a}) ({b})')
    elif family in ('tree_chain', 'balanced_tree'):
        declarations = 'data Tree = Leaf Int | Branch Tree Tree;\nscore :: Tree -> Int;\nscore t = case t of { Leaf y -> y; Branch a b -> addInt (score a) (score b) };\n'
        leaves = [f'Leaf (addInt x {i})' for i in range(n)]
        if family == 'balanced_tree':
            tree = balanced(leaves, lambda a,b:f'Branch ({a}) ({b})')
        else:
            tree = leaves[-1]
            for leaf in reversed(leaves[:-1]):
                tree = f'Branch ({leaf}) ({tree})'
        expression = f'score ({tree})'
    elif family == 'wide_case':
        tags = ' | '.join(f'Tag{i}' for i in range(n))
        arms = '; '.join(f'Tag{i} -> {2*i+1}' for i in range(n))
        declarations = (f'data Tag = {tags};\npick :: Int -> Tag;\npick x = {tag_selector(0, n-1)};\n'
                        f'score :: Tag -> Int;\nscore tag = case tag of {{ {arms} }};\n')
        return (HEADER + declarations
                + 'selectedScore :: Int -> Int;\nselectedScore i = score (pick i);\n'
                + 'entry :: Int -> Int;\nentry x = addInt x (selectedScore x);\n'
                + 'printAll :: Int -> IO ();\n'
                + f'printAll i = if eqInt i {n} then ioReturn () '
                + 'else ioBind (printInt (selectedScore i)) (\\_ -> printAll (addInt i 1));\n'
                + 'main :: IO ();\nmain = ioBind (getArg 0) (\\text -> if eqString text "--all" '
                + 'then printAll 0 else printInt (entry (readInt text)))\n}\n')
    elif family == 'class_instances':
        declarations = ('class Score a where { score :: a -> Int };\n'
                        'measure :: forall a. Score a => a -> Int;\nmeasure value = score value;\n')
        instances = [f'data Box{i} = Box{i} Int;\n'
                     f'instance Score Box{i} where {{ score (Box{i} y) = mulInt y {i+1} }};\n'
                     for i in range(n)]
        declarations += ''.join(instances)
        terms = [f'measure (Box{i} (addInt x {i}))' for i in range(n)]
        expression = balanced(terms, lambda a,b: f'addInt ({a}) ({b})')
    elif family == 'dependency_diamonds':
        layers = ['start :: Bool -> Int -> Int;\nstart flag x = x;\n']
        previous = 'start'
        for i in range(n):
            layers.append(f'left{i} :: Bool -> Int -> Int;\nleft{i} flag x = addInt ({previous} flag x) {i+1};\n'
                          f'right{i} :: Bool -> Int -> Int;\nright{i} flag x = subInt ({previous} flag x) {i+1};\n'
                          f'join{i} :: Bool -> Int -> Int;\njoin{i} flag x = if flag then left{i} flag x else right{i} flag x;\n')
            previous = f'join{i}'
        declarations = ''.join(layers)
        expression = f'{previous} (ltInt x 0) x'
    elif family == 'captured_closures':
        leaves = [
            f'let {{ saved = subInt x {i} }} in Closure {i} (\\arg -> mulInt saved arg)'
            for i in range(1, n + 1)
        ]
        tree = balanced(leaves, lambda a, b: f'Both ({a}) ({b})')
        declarations = (
            'data Closures = Closure Int (Int -> Int) | Both Closures Closures;\n'
            'makeClosures :: Int -> Closures;\n'
            f'makeClosures x = {tree};\n'
            'applyClosures :: Closures -> Int;\n'
            'applyClosures cs = case cs of { Closure arg f -> f arg; '
            'Both l r -> addInt (applyClosures l) (applyClosures r) };\n'
        )
        expression = 'applyClosures (makeClosures x)'

    elif family == 'wide_product':
        indices = range(1, n + 1)
        types = ' '.join(['Int'] * n)
        binders = ' '.join(f'v{i}' for i in indices)
        fields = ' '.join(f'(addInt x {i})' for i in indices)
        terms = [f'mulInt v{i} {n + 1 - i}' for i in indices]
        total = balanced(terms, lambda a, b: f'addInt ({a}) ({b})')
        declarations = (
            f'data Product = Product {types};\n'
            'weigh :: Product -> Int;\n'
            f'weigh p = case p of {{ Product {binders} -> {total} }};\n'
        )
        expression = f'weigh (Product {fields})'
    elif family == 'rank2_arguments':
        declarations = (
            'probe :: (forall a. a -> a -> a) -> Int -> Int -> Int;\n'
            'probe pick x offset = let { value = pick (addInt x offset) '
            '(addInt (mulInt 2 x) offset) } in '
            'if pick (ltInt x 0) (ltInt 0 x) then addInt value 1 else value;\n'
        )
        terms = []
        for i in range(n):
            selected = 'left' if i % 2 == 0 else 'right'
            terms.append(f'probe (\\left right -> {selected}) x {i}')
        expression = balanced(terms, lambda a, b: f'addInt ({a}) ({b})')
    elif family in ('irregular_literal_table', 'decoder_pipeline'):
        declarations, expression = data_shapes.program_body(family, n)
    elif family in ('nested_poly_types', 'rank2_callbacks'):
        declarations, expression = rank_shapes.program_body(family, n, balanced)
    elif family == 'state_updates':
        updates = ''.join(f'v{i} <- readIntArray cell 0; writeIntArray cell 0 (subInt {i} v{i});\n'
                          for i in range(n))
        return (HEADER + 'entry :: Int -> IO Int;\nentry x = do { cell <- newIntArray 1 x;\n'
                + updates + 'readIntArray cell 0 };\n'
                + 'main :: IO ();\nmain = ioBind (getArg 0) (\\text -> ioBind (entry (readInt text)) printInt)\n}\n')
    elif family == 'literal_table':
        table = 'Nil'
        for i in reversed(range(n)):
            table = f'Cons (Item {i} {i+1}) ({table})'
        declarations = ('data Item = Item Int Int;\ndata Items = Nil | Cons Item Items;\n'
            'score :: Int -> Items -> Int;\nscore factor values = case values of { Nil -> 0; Cons item rest -> case item of { Item a b -> addInt (addInt (mulInt factor a) b) (score factor rest) } };\n'
            f'table :: Items;\ntable = {table};\n')
        expression = 'score x table'
    elif family == 'higher_order_chain':
        declarations = 'compose :: forall a b c. (b -> c) -> (a -> b) -> a -> c;\ncompose f g y = f (g y);\nstep :: Int -> Int;\nstep y = addInt y 1;\nidentity :: forall a. a -> a;\nidentity y = y;\n'
        expression = 'identity'
        for _ in range(n):
            expression = f'compose step ({expression})'
        expression = f'({expression}) x'
    else:
        raise ValueError(family)
    return HEADER + declarations + f'entry :: Int -> Int;\nentry x = {expression};\n' + MAIN


def expected(family, n, x):
    """Closed-form specifications; no compiled results or generated helpers used."""
    if family == 'baseline':
        return x
    if family in ('flat_functions', 'inferred_functions', 'local_functions', 'mono_calls', 'poly_calls', 'tree_chain', 'balanced_tree'):
        return n*x + n*(n-1)//2
    if family in ('dependency_chain', 'inferred_chain', 'higher_order_chain'):
        return x+n
    if family == 'inferred_poly_chain':
        positive = (x < 0) != (n % 2 == 1)
        return x+n if positive else -(x+n)
    if family == 'inferred_poly_functions':
        negative = max(0, min(n, x + 1))
        return n*x + n*(n-1)//2 - 2*(negative*x + negative*(negative-1)//2)
    if family == 'recursive_ring':
        return max(0,x) % n
    if family == 'wide_case':
        return x + 2 * max(0, min(x, n-1)) + 1
    if family == 'class_instances':
        return x*n*(n+1)//2 + n*(n-1)*(n+1)//3
    if family == 'dependency_diamonds':
        change = n*(n+1)//2
        return x + change if x < 0 else x - change
    if family == 'captured_closures':
        return x * n * (n + 1) // 2 - n * (n + 1) * (2 * n + 1) // 6
    if family == 'wide_product':
        return x * n * (n + 1) // 2 + n * (n + 1) * (n + 2) // 6
    if family == 'rank2_arguments':
        right_sites = n // 2
        left_sites = n - right_sites
        increments = (left_sites if x < 0 else 0) + (right_sites if x > 0 else 0)
        return (left_sites + 2 * right_sites) * x + n * (n - 1) // 2 + increments
    if family in ('irregular_literal_table', 'decoder_pipeline'):
        return data_shapes.expected(family, n, x)
    if family in ('nested_poly_types', 'rank2_callbacks'):
        return rank_shapes.expected(family, n, x)
    if family == 'state_updates':
        return n//2 - x if n % 2 else x + n//2
    if family == 'literal_table':
        return x*n*(n-1)//2 + n*(n+1)//2
    raise ValueError(family)


def expected_output(family, size, argument):
    if family == 'wide_case' and argument == '--all':
        return ''.join(f'{2*i+1}\n' for i in range(size))
    return f'{expected(family, size, argument)}\n'


def coordinates(sizes=None, families=None):
    if sizes is None:
        sizes = REGISTRY['matrices']['default']['sizes']
    selected = REGISTRY['matrices']['default']['families'] if families is None else list(families)
    unknown = [f for f in selected if f != 'baseline' and f not in FAMILIES]
    if unknown:
        raise ValueError('unknown families: ' + ', '.join(unknown))
    return [(family, n) for family in selected for n in ((0,) if family == 'baseline' else sizes)]


def generate(out, sizes=None, families=None):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    cases = []
    for family, n in coordinates(sizes, families):
        identity = f'{family}-{n}'
        directory = out/identity; directory.mkdir()
        source = directory/'Main.hs'; source.write_text(program(family,n))
        inputs = [-1,0,n+3] if family == 'recursive_ring' else [-1,0,7]
        if family == 'wide_case':
            inputs = [-1, n//2, n, '--all']
        elif family == 'decoder_pipeline':
            inputs = data_shapes.inputs(family, n)
        elif family == 'rank2_callbacks':
            inputs = [-1, n//2, n]
        elif family in ('captured_closures', 'wide_product'):
            inputs = [-n-1, 0, n+1]
        cases.append({'id':identity,'family':family,'size':n,'source':str(source.resolve()),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_bytes':source.stat().st_size,
            'inputs':inputs, 'expected_stdout':[expected_output(family,n,x) for x in inputs],
            'syntax':'shared-haskell-v1; identical source bytes for GHC and MLF',
            'route':'one Main module, imports fixed MLF.Primitive; main reads runtime argv'})
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    return cases
