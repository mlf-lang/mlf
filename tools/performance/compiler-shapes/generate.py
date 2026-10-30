"""Deterministic, identical shared-Haskell programs with independent IO oracles."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
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
FAMILIES = ('flat_functions', 'local_functions', 'dependency_chain', 'inferred_chain', 'recursive_ring',
            'mono_calls', 'poly_calls', 'tree_chain', 'balanced_tree',
            'literal_table', 'higher_order_chain')


def balanced(expressions, combine):
    if len(expressions) == 1:
        return expressions[0]
    half = len(expressions) // 2
    return combine(balanced(expressions[:half], combine), balanced(expressions[half:], combine))


def program(family, n):
    """No generated declaration is intentionally unreachable from the IO entry."""
    if family == 'baseline':
        declarations, expression = '', 'x'
    elif family in ('flat_functions', 'local_functions', 'dependency_chain', 'inferred_chain'):
        declarations = ''
        for i in range(n):
            if family != 'inferred_chain':
                declarations += f'f{i} :: Int -> Int;\n'
            rhs = f'addInt x {i}' if family in ('flat_functions','local_functions') else ('addInt x 1' if i == 0 else f'f{i-1} (addInt x 1)')
            declarations += f'f{i} x = {rhs};\n'
        expression = (balanced([f'f{i} x' for i in range(n)], lambda a,b:f'addInt ({a}) ({b})')
                      if family in ('flat_functions','local_functions') else f'f{n-1} x')
        if family == 'local_functions':
            expression = 'let {\n'+declarations+'} in '+expression
            declarations = ''
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
    if family in ('flat_functions', 'local_functions', 'mono_calls', 'poly_calls', 'tree_chain', 'balanced_tree'):
        return n*x + n*(n-1)//2
    if family in ('dependency_chain', 'inferred_chain', 'higher_order_chain'):
        return x+n
    if family == 'recursive_ring':
        return max(0,x) % n
    if family == 'literal_table':
        return x*n*(n-1)//2 + n*(n+1)//2
    raise ValueError(family)


def generate(out, sizes=(8,32,128), families=None):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    cases = []
    selected = families if families is not None else tuple(f for f in FAMILIES if f != 'local_functions')
    for family,n in ([('baseline',0)] if families is None else []) + [(f,n) for f in selected for n in sizes]:
        identity = f'{family}-{n}'
        directory = out/identity; directory.mkdir()
        source = directory/'Main.hs'; source.write_text(program(family,n))
        inputs = [-1,0,n+3] if family == 'recursive_ring' else [-1,0,7]
        cases.append({'id':identity,'family':family,'size':n,'source':str(source.resolve()),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_bytes':source.stat().st_size,
            'inputs':inputs, 'expected_stdout':[f'{expected(family,n,x)}\n' for x in inputs],
            'syntax':'shared-haskell-v1; identical source bytes for GHC and MLF',
            'route':'one Main module, imports fixed MLF.Primitive; main reads runtime argv'})
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    return cases
