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
    elif family == 'class_declaration_reservations':
        declarations = '''data Token = Token Int;
class Score a where { score :: a -> Int };
instance Score Token where { score (Token value) = value };
'''
        names = [f'compilerShapeReservationForIndependentTopLevelPredecessor{i}' for i in range(n)]
        for i, name in enumerate(names):
            declarations += (f'{name} :: Int -> Int;\n'
                             f'{name} x = score (Token (addInt x {i}));\n')
        expression = balanced([f'{name} x' for name in names],
                              lambda a, b: f'addInt ({a}) ({b})')
    elif family == 'datatype_validation_fanout':
        declarations = 'data Token = ' + ' | '.join(f'Tag{i} Int' for i in range(n)) + ';\n'
        declarations += ''.join(
            f'probe{i} :: Token -> Int;\n'
            f'probe{i} t = case t of {{ Tag{i} x -> addInt x {i}; _ -> {i} }};\n'
            for i in range(n))
        calls = [f'probe{i} (if ltInt x 0 then Tag{(i+1)%n} x else Tag{i} x)' for i in range(n)]
        expression = balanced(calls, lambda a, b: f'addInt ({a}) ({b})')
    elif family == 'shared_datatype_fragments':
        alternatives = ' | '.join(f'Alternate{i}' for i in range(n))
        rows = [f'data Shared = Primary Int | {alternatives};']
        for i in range(n):
            rows.extend((f'data Local{i} = Local{i} Int;',
                         f'project{i} :: Shared -> Local{i} -> Int;',
                         f'project{i} shared (Local{i} y) = case shared of {{ Primary z -> addInt z y; _ -> y }};'))
        terms = [f'(project{i} shared (Local{i} {i}))' for i in range(n)]
        total = balanced(terms, lambda a, b: f'(addInt {a} {b})')
        rows.append('entry :: Int -> Int;\n'
                    f'entry x = let {{ shared = if ltInt x 0 then Alternate0 else Primary x }} in {total};')
        return HEADER + '\n'.join(rows) + '\n' + MAIN
    elif family == 'boxed_closure_factory':
        declarations = r'''data Box = Absent | Box (Int -> Int);
make :: Int -> Int -> Box;
make left right = Box (\x -> if ltInt x 0 then addInt (mulInt left right) x else addInt (subInt left right) (mulInt x x));
readBox :: Box -> Int -> Int;
readBox box input = case box of { Absent -> subInt 0 input; Box f -> f input };
data Chain = End | More Box Chain;
sumChain :: Int -> Chain -> Int;
sumChain x chain = case chain of { End -> 0; More box rest -> addInt (readBox box x) (sumChain x rest) };
'''
        chain = 'End'
        for i in range(n, 0, -1):
            chain = f'More (make x {i}) ({chain})'
        expression = f'sumChain x ({chain})'
    elif family == 'local_dictionary_branch_fanout':
        definitions = ['level0 z = if ltInt z 0 then stringLength "a" else stringLength "bb"']
        for i in range(1, n + 1):
            definitions.append(f'level{i} z = if ltInt z {i} '
                               f'then level{i-1} (addInt z {i}) else level{i-1} (subInt z {i})')
        return (HEADER + 'hotTransaction start = let {\n' + ';\n'.join(definitions)
                + f'\n}} in level{n} start;\nentry x = hotTransaction x;\n' + MAIN)
    elif family == 'polymorphic_import_fanout':
        declarations = ''.join(f'helper{i} x = x;\n' for i in range(n))
        terms = [f'helper{i} (addInt x {i})' for i in range(n)]
        expression = balanced(terms, lambda left, right: f'addInt ({left}) ({right})')
        return HEADER + declarations + f'entry x = {expression};\n' + MAIN
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
    elif family == 'polymorphic_fanout':
        terms = [f'apply (apply measure value) (addInt base {i})' for i in range(n)]
        total = balanced(terms, lambda left, right: f'addInt ({left}) ({right})')
        declarations = f'apply f value = f value;\nfanout measure value base = {total};\n'
        expression = ('addInt (fanout addInt x x) '
                      '(fanout (\\flag offset -> if flag then offset else subInt 0 offset) (ltInt x 0) x)')
    elif family == 'polymorphic_box_fanout':
        declarations = '''data Box a = Box a;
step :: forall a. Box a -> (a -> Int) -> Int;
step (Box item) next = next item;
'''
        terms = [f'step box (\\item -> measure item {i})' for i in range(n)]
        total = balanced(terms, lambda left, right: f'addInt ({left}) ({right})')
        expression = ('addInt (fanout addInt (Box x)) '
                      '(fanout (\\flag offset -> if flag then offset else subInt 0 offset) (Box (ltInt x 0)))')
        return HEADER + declarations + f'fanout measure box = {total};\nentry x = {expression};\n' + MAIN
    elif family == 'inferred_dictionary_prefix':
        cases = '\n'.join(f'    {i} -> punct "mark{i}";' for i in range(n))
        declarations = f'''loop consume fuel code state = if ltInt fuel 1 then state else let {{
  punct text = loop consume (subInt fuel 1) code (consume state text)
}} in case code of {{
{cases}
    _ -> punct "default"
  }};
'''
        expression = rf'loop (\state text -> addInt state (stringLength text)) 2 (remInt x {n}) x'
        return HEADER + declarations + f'entry x = {expression};\n' + MAIN
    elif family == 'polymorphic_scanner_cases':
        cases = '\n'.join(f'      {200 + i} -> punct "mark{i}";' for i in range(n))
        declarations = r'''data Token = Token String Int Int Int Int;
data Cursor = Cursor Int Int Int;
data Checked a b = Failed a | Succeeded b;
data Spelling = Spelling String NameTable;
data Scanned = Scanned Int Token;
data NameTable = Names Int;
data TokenOutput h = TokenOutput (Int -> Token -> h -> h) (Int -> Token -> h -> h)
  (Token -> h -> h) (Token -> h -> h) (h -> Token -> Checked String Scanned);
spellingAt :: String -> Int -> NameTable -> Spelling;
spellingAt source i names = Spelling (stringSlice source i 1) names;
skip :: String -> String -> Int -> Cursor -> Checked String Cursor;
skip file source size cursor = Succeeded cursor;
collect output@(TokenOutput word number punctuation _ finish) skipQuoted file source size known seen (Cursor start row column) = let {
  loop i line col names history =
    if i >= size then finish history (Token "" line col line col) else let {
      c = stringCodeAt source i;
      next = i + 1;
      slow = resume output skipQuoted file source size names history (Cursor i line col);
      emit save scalar end table spelling = let {
        lastColumn = col + (end - i);
        token = Token spelling line col line lastColumn;
        more = save scalar token history
      } in seq lastColumn (seq more (loop end line lastColumn table more));
      punctuationAt _ token prefix = punctuation token prefix;
      punct spelling = emit punctuationAt c next names spelling
    } in case c of {
      32 -> loop next line (col + 1) names history;
      40 -> punct "(";
      41 -> punct ")";
      65 -> emit word c next names "A";
      57 -> emit number c next names "9";
''' + cases + r'''
      _ -> slow
    }
} in loop start row column known seen;
resume output@(TokenOutput _ _ _ save finish) skipQuoted file source size names seen cursor =
  case skipQuoted file source size cursor of {
    Failed reason -> Failed reason;
    Succeeded (Cursor i row col) -> if i >= size then finish seen (Token "" row col row col)
      else case spellingAt source i names of {
        Spelling spelling nextNames -> let {
          token = Token spelling row col row (col + 1);
          more = save token seen
        } in seq more (collect output skipQuoted file source size nextNames more (Cursor (i + 1) row (col + 1)))
      }
  };
result value = case value of { Failed _ -> subInt 0 1; Succeeded (Scanned count _) -> count };
'''
        expression = rf'''let {{
  measure (Token text _ _ _ _) count = addInt count (stringLength text);
  step _ token count = measure token count;
  finish count token = Succeeded (Scanned count token);
  input = concatString "A(9)" (if ltInt x 0 then "#" else stringFromCode (addInt 200 (remInt x {n})))
}} in result (collect (TokenOutput step step measure measure finish) skip "" input
  (stringLength input) (Names 0) x (Cursor 0 1 1))'''
    elif family == 'polymorphic_tree_fold':
        declarations = '''data Tree a = Leaf a | Branch (Tree a) (Tree a);
foldTree :: forall a b. (a -> b -> b) -> b -> Tree a -> b;
foldTree step seed tree = case tree of {
  Leaf value -> step value seed;
  Branch left right -> foldTree step (foldTree step seed right) left
};
foldPair step seed left right = foldTree step seed (Branch (Leaf left) (Leaf right));
'''
        calls = [f'foldPair addInt x (addInt x {i}) x' for i in range(n)]
        total = balanced(calls, lambda left, right: f'addInt ({left}) ({right})')
        return HEADER + declarations + f'entry x = {total};\n' + MAIN
    elif family == 'inferred_monadic_recursion':
        steps = '\n'.join(f'    a{i+1} <- pure (addInt a{i} x);' for i in range(n))
        declarations = f'''data Work a = Done a;
instance Functor Work where {{ fmap f (Done x) = Done (f x) }};
instance Applicative Work where {{ pure x = Done x; (<*>) (Done f) (Done x) = Done (f x) }};
instance Monad Work where {{ (>>=) (Done x) next = next x }};
data Tree = Leaf Int | Branch Tree Int;
core :: Tree -> Work Int;
core tree = work tree;
work tree = case tree of {{
  Leaf y -> return y;
  Branch body x -> do {{
    a0 <- core body;
{steps}
    return a{n}
  }}
}};
'''
        expression = 'case core (Branch (Leaf x) x) of { Done a -> a }'
    elif family in ('shared_callback_let_chain', 'queued_callback_let_chain'):
        bindings = []
        previous = 'x'
        for i in range(n):
            rule, state = f'rule{i}', f'state{i}'
            operand = f'(mulInt {previous} y)' if family == 'shared_callback_let_chain' else 'y'
            bindings.append(f'{rule} y = remInt (addInt {previous} {operand}) 251')
            bindings.append(f'{state} = if ltInt x {i} then {rule} x else {rule} (addInt x 1)')
            previous = state
        return HEADER + 'entry :: Int -> Int;\nentry x = let {\n' + ';\n'.join(bindings) + f'\n}} in {previous};\n' + MAIN
    elif family == 'deferred_constructor_spine':
        pattern = '(Link _ ' * (n - 1) + '(Link here _)' + ')' * (n - 1)
        declarations = f'''data Chain = End | Link Int Chain;
make :: Int -> Int -> Chain;
make remaining value = if ltInt remaining 1 then End
  else Link value (make (subInt remaining 1) (addInt value 1));
inspect :: Chain -> Int;
inspect value = case value of {{ {pattern} -> here; _ -> 0 }};
'''
        expression = f'inspect (make (if ltInt x 0 then {n - 1} else {n}) x)'
    elif family == 'signed_constructor_cases':
        declarations = '''data Path a = End | Step a (Path a);
build :: Int -> Int -> Path Int;
build count base = if ltInt count 1 then End else
  Step (addInt base count) (build (subInt count 1) base);
'''
        for i in range(n):
            value = 'item' if i == 0 else f'f{i-1} item rest'
            declarations += (f'f{i} :: forall a. a -> Path a -> a;\n'
                             f'f{i} prior path = case path of {{ End -> prior; Step item rest -> {value} }};\n')
        expression = f'f{n-1} x (build (if ltInt x 0 then {n//2} else {n}) x)'
    elif family == 'recursive_ring':
        declarations = ''.join(f'f{i} :: Int -> Int;\nf{i} x = if ltInt x 1 then {i} else f{(i+1)%n} (subInt x 1);\n' for i in range(n))
        expression = 'f0 x'
    elif family == 'mixed_parser_recursion':
        declarations = r'''data Reply a = Stop | Next a Int;
data Parser a = Parser (Int -> Reply a);
run :: forall a. Parser a -> Int -> Reply a;
run (Parser f) state = f state;
pureP :: forall a. a -> Parser a;
pureP x = Parser (\state -> Next x state);
mapP :: forall a b. (a -> b) -> Parser a -> Parser b;
mapP f p = Parser (\state -> case run p state of { Stop -> Stop; Next x s -> Next (f x) s });
bindP :: forall a b. Parser a -> (a -> Parser b) -> Parser b;
bindP p f = Parser (\state -> case run p state of { Stop -> Stop; Next x s -> run (f x) s });
choice :: forall a. Parser a -> Parser a -> Parser a;
choice p q = Parser (\s -> case run p s of { Stop -> run q s; hit -> hit });
tick :: Parser Int;
tick = Parser (\s -> if ltInt s 1 then Stop else Next s (subInt s 1));
'''
        declarations += ''.join(
            f'rule{i} :: Parser Int;\n'
            f'rule{i} = choice (bindP tick (\\_ -> tail{i} {i})) (pureP {i});\n'
            f'tail{i} first = mapP (addInt (addInt first 1)) rule{(i+1)%n};\n'
            for i in range(n))
        expression = 'case run rule0 x of { Next value _ -> value; Stop -> (-1) }'
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
    if family in ('flat_functions', 'inferred_functions', 'local_functions', 'mono_calls', 'poly_calls',
                  'class_declaration_reservations',
                  'tree_chain', 'balanced_tree', 'polymorphic_import_fanout'):
        return n*x + n*(n-1)//2
    if family == 'datatype_validation_fanout':
        return x if n == 1 else n*max(0, x) + n*(n-1)//2
    if family == 'shared_datatype_fragments':
        return n*max(0, x) + n*(n-1)//2
    if family == 'boxed_closure_factory':
        offsets = n*(n+1)//2
        return x*(offsets + n) if x < 0 else n*(x + x*x) - offsets
    if family == 'local_dictionary_branch_fanout':
        for threshold in range(n, 0, -1):
            x += threshold if x < threshold else -threshold
        return 1 if x < 0 else 2
    if family in ('dependency_chain', 'inferred_chain', 'higher_order_chain'):
        return x+n
    if family == 'inferred_poly_chain':
        positive = (x < 0) != (n % 2 == 1)
        return x+n if positive else -(x+n)
    if family == 'inferred_poly_functions':
        negative = max(0, min(n, x + 1))
        return n*x + n*(n-1)//2 - 2*(negative*x + negative*(negative-1)//2)
    if family == 'polymorphic_fanout':
        offsets = n*x + n*(n-1)//2
        return n*x + offsets + (offsets if x < 0 else -offsets)
    if family == 'polymorphic_box_fanout':
        return n*x + (n*(n-1) if x < 0 else 0)
    if family == 'inferred_dictionary_prefix':
        label_length = len(str(x % n)) + 4 if x >= 0 else (7 if x % n else 5)
        return x + 2 * label_length
    if family == 'polymorphic_scanner_cases':
        return x + 4 + (1 if x < 0 else len(f'mark{x % n}'))
    if family == 'polymorphic_tree_fold':
        total = 3*n*x + n*(n-1)//2
        return (total + 2**63) % 2**64 - 2**63
    if family == 'inferred_monadic_recursion':
        return ((n + 1)*x + 2**63) % 2**64 - 2**63
    if family == 'shared_callback_let_chain':
        computed = max(0, min(n, x+1))
        magnitude = abs(x) * pow(abs(x+2), computed, 251) * pow(abs(x+1), n-computed, 251) % 251
        return -magnitude if x < 0 and n % 2 == 0 else magnitude
    if family == 'queued_callback_let_chain':
        value = (n+1)*x + max(0, min(n, x+1))
        return -(abs(value) % 251) if value < 0 else value % 251
    if family == 'deferred_constructor_spine':
        return 0 if x < 0 else x+n-1
    if family == 'signed_constructor_cases':
        return x + int(x >= 0 or n >= 2)
    if family == 'recursive_ring':
        return max(0,x) % n
    if family == 'mixed_parser_recursion':
        cycles, remainder = divmod(max(0, x), n)
        # Each full circuit adds 1 through n. The stopping rule returns its index.
        return cycles * n * (n + 1) // 2 + remainder * (remainder + 1) // 2 + remainder
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
        elif family == 'inferred_dictionary_prefix':
            inputs = [-n-1, -n, n-1]
        elif family == 'mixed_parser_recursion':
            inputs = [-1, 0, n-1, n, 2*n+1]
        elif family == 'local_dictionary_branch_fanout':
            limit = n*(n+1)//2 + 1
            inputs = [-limit, 0, limit]
        elif family in ('shared_callback_let_chain', 'queued_callback_let_chain'):
            inputs = [1, 7, 19]
        elif family in ('captured_closures', 'wide_product'):
            inputs = [-n-1, 0, n+1]
        cases.append({'id':identity,'family':family,'size':n,'source':str(source.resolve()),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_bytes':source.stat().st_size,
            'inputs':inputs, 'expected_stdout':[expected_output(family,n,x) for x in inputs],
            'syntax':'shared-haskell-v1; identical source bytes for GHC and MLF',
            'route':'one Main module, imports fixed MLF.Primitive; main reads runtime argv'})
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    return cases
