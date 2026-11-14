HEADER = '-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,\n             KindSignatures, FlexibleContexts, FlexibleInstances,\n             MultiParamTypeClasses, OverloadedStrings #-}\nmodule Main (main) where {\nimport MLF.Primitive;\n'

MAIN = '\nmain :: IO ();\nmain = ioBind (getArg 0) (\\text -> printInt (entry (readInt text)))\n}\n'

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
