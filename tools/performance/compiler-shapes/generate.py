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


def packet_declarations(n):
    declarations = '''data Packet = Missing | Payload Int Int;
packet x = if eqInt x 0 then Missing else Payload (addInt x 3) (subInt 3 x);
'''
    for i in range(n):
        declarations += (f'probe{i} :: Packet -> Int;\n'
                         f'probe{i} packet = case packet of {{ Missing -> {i}; Payload left right -> '
                         f'if ltInt left {i} then addInt left {i} else subInt right {i} }};\n')
    return declarations


def local_recursive_checks(n):
    count = max(n, 1)
    helpers = []
    for i in range(count):
        following = (i + 1) % count
        helpers.append(f"""visit{i} term = let {{
  both a b = do {{ l <- visit{following} a; r <- visit{following} b; return (addInt l r) }};
  fallback a b = case visit{following} a of {{ Good value -> Good value; Refused -> do {{ value <- visit{following} b; return (addInt value {i}) }} }}
}} in case term of {{
  Leaf x -> Good (addInt x {i}); Pair a b -> both a b; Choice a b -> fallback a b; Absent -> Refused
}}""")
    return HEADER + '''data Subject = Leaf Int | Pair Subject Subject | Choice Subject Subject | Absent;
data Check a = Refused | Good a;
instance Functor Check where { fmap f value = case value of { Refused -> Refused; Good x -> Good (f x) } };
instance Applicative Check where { pure = Good; (<*>) vf vx = case vf of { Refused -> Refused; Good f -> fmap f vx } };
instance Monad Check where { (>>=) action next = case action of { Refused -> Refused; Good x -> next x } };
wrap k subject = if ltInt k 1 then subject else Choice Absent (wrap (subInt k 1) subject);
walk subject = let {
''' + ';\n'.join(helpers) + '''
} in visit0 subject;
entry x = case walk (wrap ''' + str(n) + ''' (Pair (Choice Absent (Leaf x)) (Pair (Leaf 4) (Leaf 7)))) of {
  Refused -> 0; Good value -> value
};
''' + MAIN


def program(family, n):
    """Generate one shared module with a runtime input at its IO entry."""
    if family == 'baseline':
        declarations, expression = '', 'x'
    elif family == 'module_string_literals' and n:
        common = ['coerce', 'Prelude', 'Bool', 'Dict_' + 'x' * 64]
        def select(start, stop):
            if stop - start == 1:
                kind = start % 5
                text = common[kind] if kind < 4 else 'λ' + 'abcdefghij' * 6 + '𐀀' + str(start)
                return json.dumps(text, ensure_ascii=False)
            middle = (start + stop) // 2
            return f'(if ltInt x {middle} then {select(start, middle)} else {select(middle, stop)})'
        declarations = 'pick :: Int -> String;\npick x = ' + select(0, n) + ';\n'
        expression = ('let { text = pick x; size = stringLength text } in '
                      'addInt (mulInt size 257) (stringCodeAt text (subInt size 1))')
    elif family == 'module_string_literals':
        declarations, expression = '', 'x'
    elif family == 'mixed_unicode_literal':
        # Positions include both Unicode scalars and both ends of the ASCII run.
        payload = 'λ' + 'abcdefghijklmnop' * n + '界'
        declarations = f'literal :: String;\nliteral = "{payload}";\n'
        expression = ('let { last = subInt (stringLength literal) 1; index = '
                      'if ltInt x 0 then 0 else if eqInt x 0 then last else remInt x last } '
                      'in addInt (stringLength literal) (stringCodeAt literal index)')
    elif family == 'captured_parameter_uses':
        declarations = ''.join(
            f'f{i} x = let {{ y = x }} in addInt y {i+1};\n' for i in range(n))
        calls = [f'(f{i} x)' for i in range(n)]
        expression = balanced(calls, lambda a, b: f'(addInt {a} {b})') if calls else '0'
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
    elif family in ('delayed_packet_fanout', 'retained_packet_dependency'):
        declarations = (packet_declarations(n) if family == 'delayed_packet_fanout'
                        else 'import PacketLibrary;\n')
        terms = [f'(probe{i} payload)' for i in range(n)]
        total = balanced(terms, lambda a, b: f'(addInt {a} {b})')
        return HEADER + declarations + f'entry x = let {{ payload = packet x }} in {total};\n' + MAIN
    elif family == 'wide_thunk_captures':
        declarations = '''data WideRow = WideRow Int Int;
data WideBatch = WideEnd | WideMore WideRow WideBatch;
readRows x batch = case batch of {
  WideEnd -> 0;
  WideMore row rest -> case row of {
    WideRow wide narrow -> addInt (if ltInt x 0 then wide else narrow) (readRows x rest)
  }
};
'''
        for i in range(1, n + 1):
            declarations += (f'make{i} a b c d e f g h = WideRow '
                             f'(addInt {i} (addInt (addInt (mulInt a b) (mulInt c d)) '
                             f'(addInt (mulInt e f) (mulInt g h)))) (subInt a {i});\n')
        args = ' '.join(['x'] + [f'(addInt x {i})' for i in range(1, 8)])
        rows = ''.join(f'WideMore (make{i} {args}) (' for i in range(1, n + 1))
        return HEADER + declarations + f'entry x = readRows x ({rows}WideEnd' + ')' * n + ');\n' + MAIN
    elif family == 'captured_thunk_fanout':
        declarations = '''data Row = Row Int Int Int Int;
data Batch = End | More Row Batch;
readRow selector row = case row of {
  Row one two three four -> if ltInt selector 0 then addInt one three else addInt two four
};
readBatch selector batch = case batch of {
  End -> 0;
  More row rest -> addInt (readRow selector row) (readBatch selector rest)
};
'''
        for i in range(1, n + 1):
            declarations += (f'make{i} a b c d = Row (mulInt a {i}) (mulInt a b) '
                             '(mulInt c (addInt a b)) (mulInt (addInt a b) (addInt c d));\n')
        rows = ''.join(f'More (make{i} x b c d) (' for i in range(1, n + 1)) + 'End' + ')' * n
        return (HEADER + declarations + 'entry x = let { b = addInt x 3; c = subInt 9 x; d = mulInt 2 x } '
                f'in readBatch x ({rows});\n' + MAIN)
    elif family == 'repeated_ground_dictionary_demands':
        terms = [f'stringLength "{"s" * (i % 4 + 1)}"' for i in range(n)]
        total = balanced(terms, lambda a, b: f'addInt ({a}) ({b})')
        declarations = f'''next :: Int -> Int;
next x = producer x;
producer x = if ltInt x 0 then next (subInt 0 x) else addInt x ({total});
'''
        expression = '''let {
  run z = producer z;
  choose z = if ltInt z 0 then run z else run (addInt z 1)
} in addInt (choose x) (choose (subInt 0 x))'''
        return HEADER + declarations + f'entry x = {expression};\n' + MAIN
    elif family == 'local_dictionary_branch_fanout':
        definitions = ['level0 z = if ltInt z 0 then stringLength "a" else stringLength "bb"']
        for i in range(1, n + 1):
            definitions.append(f'level{i} z = if ltInt z {i} '
                               f'then level{i-1} (addInt z {i}) else level{i-1} (subInt z {i})')
        return (HEADER + 'hotTransaction start = let {\n' + ';\n'.join(definitions)
                + f'\n}} in level{n} start;\nentry x = hotTransaction x;\n' + MAIN)
    elif family in ('recursive_dictionary_forwarding', 'recursive_dictionary_alias',
                    'closed_dictionary_result'):
        declarations = """data Box a = Box Int a;
data Tag a = Tag Int a;
class Step a where { step :: a -> Int };
instance Step (Box a) where { step (Box value ignored) = value };
instance Step (Tag a) where { step (Tag value ignored) = subInt 0 value };
"""
        terms = [f'(step ({"Box" if i % 2 == 0 else "Tag"} (addInt x {i}) x))' for i in range(n)]
        subtotal = balanced(terms, lambda a, b: f'(addInt {a} {b})') if terms else '0'
        if family == 'closed_dictionary_result':
            return HEADER + declarations + f'worker x = {subtotal};\nentry x = addInt x (worker x);\n' + MAIN
        if family == 'recursive_dictionary_alias':
            return (HEADER + declarations
                    + 'first direction fuel x = if ltInt fuel 1 then '
                    + f'addInt (if direction then x else subInt 0 x) {subtotal} else second (subInt fuel 1) x;\n'
                    + 'bridge = first True;\n'
                    + 'second fuel x = if ltInt fuel 1 then bridge 0 (addInt x 1) else bridge (subInt fuel 1) x;\n'
                    + 'entry x = second 2 x;\n' + MAIN)
        return (HEADER + declarations
                + f'first fuel x = if ltInt fuel 1 then addInt x {subtotal} else second (subInt fuel 1) x;\n'
                + 'second fuel x = if ltInt fuel 1 then first 0 (addInt x 1) else first (subInt fuel 1) x;\n'
                + 'entry x = second 2 x;\n' + MAIN)
    elif family in ('repeated_dictionary_arguments', 'bounded_dictionary_arguments'):
        declarations = """data Box = Box Int;
class Pass a where { pass :: a -> a };
instance Pass Box where { pass (Box x) = Box (addInt x 1) };
"""
        if family == 'bounded_dictionary_arguments':
            body = f'callback x{n}'
            for i in reversed(range(n)):
                body = f'case pass (Box x{i}) of {{ Box x{i+1} -> {body} }}'
            return (HEADER + declarations + f'worker callback x0 = {body};\n'
                    + 'entry x = worker (\\y -> y) x;\n' + MAIN)
        calls = '(pass ' * n + 'x' + ')' * n
        return (HEADER + declarations + f'worker x = {calls};\n'
                + 'entry x = case worker (Box x) of { Box y -> y };\n' + MAIN)
    elif family == 'duplicated_type_arguments':
        # Each call shares its value but uses its type in both result slots.
        expression = 'x'
        for _ in range(n):
            expression = f'(duplicate {expression})'
        for _ in range(n):
            expression = f'(left {expression})'
        declarations = ('data Fork a b = ForkValue a b;\n'
                        'duplicate :: forall a. a -> Fork a a;\n'
                        'duplicate x = ForkValue x x;\n'
                        'left :: forall a b. Fork a b -> a;\n'
                        'left (ForkValue x _) = x;\n')
        return HEADER + declarations + f'entry x = {expression};\n' + MAIN
    elif family == 'polymorphic_import_spine':
        parameters = ''.join(f' unused{i}' for i in range(n))
        operands = ''.join(
            f' ({"ltInt" if i % 2 else "addInt"} x {i})' for i in range(n))
        # Inference gives each ignored argument its own type variable. The
        # caller imports that scheme and successively applies its wide arrow.
        declarations = f'keep seed{parameters} = seed;\n'
        return HEADER + declarations + f'entry x = keep x{operands};\n' + MAIN
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
    elif family == 'nested_worker_applications':
        if n == 0:
            return HEADER + 'entry :: Int -> Int;\nentry x = 0;\n' + MAIN
        rows = [
            'data Tokens = Stop | Token Bool Tokens;',
            'data Jobs = Done | Direct Int Jobs | Saved Int (Int -> Int) Jobs;',
            'makeTokens :: Int -> Bool -> Tokens;',
            'makeTokens n flag = if ltInt n 1 then Stop else Token flag (makeTokens (subInt n 1) (if flag then False else True));',
            'sumJobs :: Int -> Jobs -> Int;',
            'sumJobs q jobs = case jobs of { Done -> 0; Direct value rest -> addInt value (sumJobs q rest);',
            '  Saved value function rest -> addInt (addInt value (mulInt 2 (function q))) (sumJobs q rest) };',
            'score :: Tokens -> Int -> Int;',
            'score input key =',
        ]
        for i in range(1, n + 1):
            subject = 'input' if i == 1 else f'rest{i-1}'
            rows.append(f'case {subject} of {{ Stop -> 0; Token flag{i} rest{i} ->')
        for i in range(1, n + 1):
            rows.append(f'let {{ work{i} again v = if again then work{i} False 3 else if ltInt v 0 then {i} else v }} in')
        jobs = 'Done'
        for i in reversed(range(1, n + 1)):
            direct = f'(work{i} flag{i} key)'
            if i % 2:
                jobs = f'Saved {direct} (work{i} flag{i}) ({jobs})'
            else:
                jobs = f'Direct {direct} ({jobs})'
        rows.append(f'sumJobs (if ltInt key 0 then 4 else (subInt 0 1)) ({jobs})' + ' }' * n + ';')
        rows.extend(['entry :: Int -> Int;',
                     f'entry x = let {{ key = remInt x 11 }} in score (makeTokens (if eqInt key 6 then {n-1} else {n}) (ltInt key 0)) key;'])
        return HEADER + '\n'.join(rows) + '\n' + MAIN
    elif family == 'recursive_lookup_workers':
        declarations = (
            'data Tree = Empty | Branch Tree Int Int Tree;\n'
            'tree :: Tree;\n'
            'tree = Branch (Branch Empty 2 17 Empty) 5 41 (Branch Empty 8 73 Empty);\n')
        calls = []
        for i in range(n):
            declarations += (
                f'walk{i} :: Int -> Tree -> Int;\n'
                f'walk{i} q t = case t of {{ Empty -> 0; Branch l key value r -> '
                f'if ltInt q key then walk{i} q l else if ltInt key q then walk{i} q r else value }};\n')
            calls.append(f'(walk{i} (addInt x {i}) tree)')
        expression = balanced(calls, lambda a, b: f'(addInt {a} {b})') if calls else '0'
    elif family == 'stable_recursive_workers':
        rows = [HEADER, 'data Job = End | Job (Int -> Int) Job;',
                'total :: Int -> Job -> Int;',
                'total q list = case list of { End -> 0; Job f rest -> addInt (f q) (total q rest) };']
        for i in range(n):
            rows.extend([f'worker{i} :: Int -> Int;',
                         f'worker{i} x = if ltInt x 1 then {i+1} else addInt '
                         f'(worker{i} (subInt x 1)) (remInt (addInt x {i+1}) 19);'])
        params = [f'a{i}' for i in range(24)]
        state = params[0]
        for param in params[1:]:
            state = f'(remInt (addInt (mulInt {state} 3) {param}) 97)'
        function = '(' + ''.join('\\' + param + ' -> ' for param in params) + state + ')'
        args = ' '.join(f'(remInt (addInt x {i+3}) 31)' for i in range(len(params)))
        jobs = ''.join(f'(Job worker{i} ' for i in range(n)) + 'End' + ')' * n
        rows.extend(['entry :: Int -> Int;', f'entry x = addInt ({function} {args}) '
                     f'(total (remInt x 11) {jobs});', MAIN])
        return '\n'.join(rows)
    elif family == 'retained_curried_job_list':
        return (HEADER + 'import CurryLibrary;\nimport CurryFacade;\n' +
                'entry :: Int -> Int;\nentry x = run x allJobs;\n' + MAIN)
    elif family == 'retained_curried_dependencies':
        jobs = ''.join(f'More job{i} (' for i in range(n)) + 'End' + ')'*n
        return (HEADER + 'import CurryLibrary;\nimport CurryFacade;\n' +
                f'entry x = run x ({jobs});\n' + MAIN)
    elif family == 'bounded_optional_writers':
        declarations = '''data Optional a = Omit | Include a;
data Writers = End | More (Int -> Int) Writers;
writeAll :: Int -> Writers -> Int;
writeAll x writers = case writers of {
  End -> 0;
  More writer rest -> addInt (writer x) (writeAll x rest)
};
'''
        omitted = '"none"'
        included = '(encode value)'
        for word in ('a', 'b', 'c', 'd', 'e', 'f'):
            omitted = f'(concatString "{word}" {omitted})'
        for word in ('u', 'v', 'w', 'x', 'y', 'z'):
            included = f'(concatString "{word}" {included})'
        declarations += f'''formatOptional encode item = case item of {{
  Omit -> {omitted};
  Include value -> {included}
}};
'''
        for index in range(n):
            declarations += f'''write{index} x =
  addInt {index} (stringLength (formatOptional showInt
    (if ltInt x 0 then Omit else Include (addInt x {index}))));
'''
        writers = ''.join(f'(More write{i} ' for i in range(n)) + 'End' + ')' * n
        declarations += f'''entry :: Int -> Int;
entry x = writeAll x {writers};
'''
        return HEADER + declarations + MAIN
    elif family == 'inferred_constructor_writers':
        declarations = '''data Query = Read Int | Reject Int | Stop;
data Decision = Accepted Int | Failed Int;
data Writers = None | More (Query -> Decision) Writers;
writeAll :: Query -> Writers -> Int;
writeAll query writers = case writers of {
  None -> 0;
  More writer rest -> case writer query of {
    Accepted value -> addInt value (writeAll query rest);
    Failed code -> subInt (writeAll query rest) code
  }
};
'''
        for index in range(n):
            declarations += f'''write{index} query = case query of {{
  Read v -> Accepted (addInt (mulInt v {index+1}) {index});
  Reject c -> Failed (addInt c {index});
  Stop -> Accepted (subInt 0 {index+1})
}};
'''
        writers = ''.join(f'(More write{index} ' for index in range(n)) + 'None' + ')' * n
        declarations += f'''entry :: Int -> Int;
entry x = writeAll (if ltInt x 0 then Reject x else if eqInt x 0 then Stop else Read x)
  {writers};
'''
        return HEADER + declarations + MAIN
    elif family == 'mixed_recursive_decoder':
        variants = ''.join(f' | Variant{i} Int' for i in range(n))
        arms = ''.join(f'  Variant{i} payload -> schedule (addInt (mulInt payload {i+2}) 3) rest;\n'
                       for i in range(n))
        choices = ''.join(f'  if eqInt x {i} then Variant{i} (addInt x 2) else\n' for i in range(n))
        return HEADER + f'''data Node = Flush | Invalid{variants};
data Task = End | Open Node Task | AddValue Int Task;
data Outcome = Rejected Int | Value Int;
dispatch :: Node -> Task -> Outcome;
dispatch node rest = case node of {{
  Flush -> schedule 0 rest;
  Invalid -> Rejected 37;
{arms}  }};
schedule value rest = scan (AddValue value rest);
scan :: Task -> Outcome;
scan tasks = case tasks of {{
  End -> Value 0;
  Open node rest -> dispatch node rest;
  AddValue amount rest -> case scan rest of {{
    Rejected code -> Rejected code;
    Value total -> Value (addInt amount total)
  }}
}};
makeNode :: Int -> Node;
makeNode x =
{choices}  if ltInt x 0 then Flush else Invalid;
entry :: Int -> Int;
entry x = case scan (Open (makeNode x) (Open Flush (AddValue 7 End))) of {{
  Rejected code -> subInt 0 code;
  Value total -> total
}};
''' + MAIN
    elif family == 'signed_decoder_selectors':
        declarations = '''data Piece = Missing | Present Int;
data Result e a = Failure e | Success a;
instance forall e. Functor (Result e) where {
  fmap _ (Failure e) = Failure e;
  fmap f (Success a) = Success (f a)
};
instance forall e. Applicative (Result e) where {
  pure a = Success a;
  (<*>) (Failure e) _ = Failure e;
  (<*>) (Success _) (Failure e) = Failure e;
  (<*>) (Success f) (Success a) = Success (f a)
};
instance forall e. Monad (Result e) where {
  (>>=) (Failure e) _ = Failure e;
  (>>=) (Success a) next = next a
};
readPiece :: Piece -> Result Int Int;
readPiece x = case x of { Missing -> Failure 11; Present a -> Success a };
assemble :: Int -> Piece -> Piece -> Result Int Int;
assemble tag left right =
'''
        declarations += ''.join(f'''  if eqInt tag {i} then do {{
    a <- readPiece left; b <- readPiece right;
    pure (addInt (mulInt a {i+1}) (subInt b {i}))
  }} else
''' for i in range(n))
        declarations += '''  Failure 99;
entry :: Int -> Int;
entry x = case assemble x (Present (addInt x 2))
  (if eqInt x 0 then Missing else Present (subInt (mulInt 3 x) 1)) of {
  Failure code -> subInt 0 code; Success value -> value
};
'''
        return HEADER + declarations + MAIN
    elif family == 'escaping_curried_jobs':
        arity = 12
        params = [f'a{j}' for j in range(arity)]
        signature = ' -> '.join(['Int']*(arity+1))
        names = ' '.join(params)
        value = params[0]
        for name in params[1:]:
            value = f'addInt (mulInt 2 ({value})) {name}'
        rows = [f'data Job = Job ({signature});', 'data Jobs = End | More Job Jobs;',
                f'score :: {signature};', f'score {names} = {value};']
        for i in range(n):
            # Each endpoint keeps its own identity, every position is observable.
            args = params[i % arity:] + params[:i % arity]
            rows.extend([f'job{i} :: {signature};',
                         f'job{i} {names} = addInt {i} (score {" ".join(args)});'])
        jobs = ''.join(f'More (Job job{i}) (' for i in reversed(range(n))) + 'End' + ')'*n
        prefix = ' '.join(f'(addInt x {j})' for j in range(1,9))
        positive = ' '.join(f'(addInt x {j})' for j in range(9,13))
        negative = ' '.join(f'(subInt x {j})' for j in range(9,13))
        rows.extend(['run :: Int -> Jobs -> Int;', 'run x End = 0;',
                     f'run x (More (Job f) rest) = let {{ saved = f {prefix} }} in',
                     f'  addInt (addInt (saved {positive}) (saved {negative})) (run x rest);',
                     f'entry x = run x ({jobs});'])
        return HEADER + '\n'.join(rows) + '\n' + MAIN
    elif family == 'captured_application_spines':
        width = 12
        args = [f'v{i}' for i in range(width)]
        arrow = ' -> '.join(['Box']*(width+1))
        rows = ['data Box = Box Int;', f'data Op = Op ({arrow});',
                'data Inputs = Inputs ' + ' '.join(['Box']*width) + ';',
                'unbox (Box v) = v;',
                f'first :: {arrow};', 'first ' + ' '.join(args) + ' = v0;',
                f'last :: {arrow};', 'last ' + ' '.join(args) + f' = v{width-1};',
                'choose :: Int -> Op;',
                'choose x = if ltInt x 0 then Op first else Op last;']
        for i in range(n):
            ordered = [args[(i+j) % width] for j in range(width)]
            # Each call keeps its own result observable with either operator.
            ordered[0] = f'(Box (addInt (unbox {ordered[0]}) {i}))'
            ordered[-1] = f'(Box (subInt (unbox {ordered[-1]}) {i}))'
            rows.extend([f'site{i} :: Op -> Inputs -> Int;',
                         f'site{i} (Op f) (Inputs {" ".join(args)}) = unbox (f {" ".join(ordered)});'])
        seed = ' '.join(f'(Box (addInt x {j}))' for j in range(width))
        uses = [f'site{i} op inputs' for i in range(n)]
        result = balanced(uses, lambda a,b: f'addInt ({a}) ({b})')
        rows.append(f'entry x = let {{ op = choose x; inputs = Inputs {seed} }} in {result};')
        return HEADER + '\n'.join(rows) + '\n' + MAIN
    elif family == 'curried_environment_prefix':
        variables = [f'arg{i}' for i in range(1, n+1)]
        fields = [f'mulInt (unbox {name}) {i}' for i, name in enumerate(variables, 1)]
        weighted = balanced(fields, lambda left, right: f'addInt ({left}) ({right})')
        signature = ' -> '.join(['Box Int'] * n + ['Int', 'Int', 'Int'])
        actual = ' '.join(f'(Box (addInt start {i}))' for i in range(1, n+1))
        declarations = f"""data Box a = Box a;
unbox :: forall a. Box a -> a;
unbox (Box item) = item;
wide :: {signature};
wide {' '.join(variables)} extra ignored = addInt ({weighted}) extra;
partial start = wide {actual};
entry x = let {{ apply = partial x }} in
  addInt (apply x (panic "unused argument")) (apply (subInt 0 x) (panic "unused argument"));
"""
        return HEADER + declarations + MAIN
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
    elif family == 'local_recursive_checks':
        return local_recursive_checks(n)
    elif family in ('local_monadic_dictionary_uses', 'ground_monadic_dictionary_uses', 'checked_groups_then_dictionary'):
        # A concrete first action fixes the monad throughout the same do block.
        first_action = ('(case start of { Done value -> Done value })'
                        if family == 'ground_monadic_dictionary_uses' else 'start')
        steps = '\n'.join(f'    a{i} <- twice (pure (addInt a{i-1} {i}));'
                          for i in range(1, n + 1))
        declarations = f"""data Work a = Done a;
instance Functor Work where {{ fmap f (Done x) = Done (f x) }};
instance Applicative Work where {{ pure x = Done x; (<*>) (Done f) (Done x) = Done (f x) }};
instance Monad Work where {{ (>>=) (Done x) next = next x }};
walk start = let {{
  step action = do {{ value <- action; return (addInt value 1) }};
  twice action = step (step action)
}} in do {{
    a0 <- {first_action};
{steps}
    return a{n}
}};
"""
        if family == 'checked_groups_then_dictionary':
            arms = 12
            rows = ['data CheckedInput = ' + ' | '.join(f'Field{j} Int' for j in range(arms)) + ';']
            for j in range(2*arms):
                rows.extend([f'offset{j} :: Int -> Int;', f'offset{j} v = addInt v {j+1};'])
            for i in range(4*n):
                alts = [f'Field{j} v -> if ltInt v {i+j} then addInt (offset{2*j} (mulInt v {j+1})) {i} '
                        f'else subInt (offset{2*j+1} (addInt v {j})) {i}' for j in range(arms)]
                rows.extend([f'checked{i} :: CheckedInput -> Int;',
                             f'checked{i} input = case input of {{ ' + '; '.join(alts) + ' };'])
            values = [f'checked{i} input' for i in range(4*n)]
            total = balanced(values, lambda a, b: f'addInt ({a}) ({b})') if values else 'x'
            select = ''.join(f'if eqInt key {j} then Field{j} x else ' for j in range(arms-1)) + f'Field{arms-1} x'
            rows.append(f'checkedPrefix :: Int -> Int;\ncheckedPrefix x = let {{ '
                        f'key = remInt (addInt {arms} (remInt x {arms})) {arms}; input = {select} }} in {total};')
            declarations = '\n'.join(rows) + '\n' + declarations.replace(
                'a0 <- start;', 'seed <- start; a0 <- pure (checkedPrefix seed);')
        expression = 'case walk (Done x) of { Done y -> y }'
    elif family == 'single_token_infix_sites':
        steps = ['step0 :: Int -> Int;', 'step0 value = value;']
        for i in range(1, n + 1):
            steps.extend([f'step{i} :: Int -> Int;',
                          f'step{i} value = step{i - 1} value + 1;'])
        declarations = '\n'.join(steps) + '\n'
        expression = f'step{n} x'
    elif family in ('recursive_monad_peers', 'nested_recursive_monad_peers'):
        preamble = HEADER + '''data Check a = Failed | Good a;
instance Functor Check where { fmap f value = case value of { Failed -> Failed; Good x -> Good (f x) } };
instance Applicative Check where { pure = Good; (<*>) vf vx = case vf of { Failed -> Failed; Good f -> fmap f vx } };
instance Monad Check where { (>>=) value next = case value of { Failed -> Failed; Good x -> next x } };
tick :: Int -> Check Int;
tick x = Good (addInt x 1);
'''
        steps = ''.join(f'  x{i+1} <- tick x{i};\n' for i in range(n))
        if family == 'nested_recursive_monad_peers':
            def nested_peer(i):
                following = (i + 1) % 4
                return (f'walk{i} remaining x0 = let {{\n'
                        f'  local k arg = if ltInt k 1 then walk{following} (subInt remaining 1) '
                        f'(addInt arg {i+1}) else do {{ next <- tick arg; local (subInt k 1) next }}\n'
                        f'}} in if ltInt remaining 1 then Good x0 else do {{\n'
                        + steps + f'  local 1 x{n}\n}};\n')

            peers = ''.join(nested_peer(i) for i in range(4))
            return preamble + peers + 'entry x = case walk0 4 x of { Failed -> 0; Good answer -> answer };\n' + MAIN

        def peer(name, other, offset):
            return (f'{name} remaining x0 = if ltInt remaining 1 then Good x0 else do {{\n'
                    + steps + f'  {other} (subInt remaining 1) (addInt x{n} {offset})\n}};\n')

        return preamble + peer('leftPeer', 'rightPeer', 2) + peer('rightPeer', 'leftPeer', 3) + '''
entry x = case leftPeer 4 x of { Failed -> 0; Good answer -> answer };
''' + MAIN
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
    elif family == 'checked_constructor_dispatch':
        declarations = (
            'data Wrapped = Wrapped Int (Int -> Step);\n'
            'data Step = Leaf Int | More Wrapped;\n'
            'make :: Int -> Wrapped;\n'
            'make value = Wrapped value (\\key -> if ltInt key 1 then Leaf key else More (make (subInt key 1)));\n'
            'walk0 :: Wrapped -> Int;\n'
            'walk0 wrapped = case wrapped of { Wrapped value advance -> value };\n'
        )
        for i in range(1, n + 1):
            declarations += (
                f'walk{i} :: Wrapped -> Int;\n'
                f'walk{i} wrapped = case wrapped of {{ Wrapped value advance -> case advance value of '
                f'{{ Leaf key -> key; More next -> addInt value (walk{i-1} next) }} }};\n'
            )
        expression = f'walk{n} (make x)'
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
    elif family == 'visible_instance_inventory':
        rows = ['class Score a where { score :: a -> Int };',
                'instance Score Int where { score x = x };']
        for i in range(n):
            rows.extend((f'data Box{i} a = B{i} a;',
                         f'instance Score a => Score (Box{i} a) where '
                         f'{{ score (B{i} v) = addInt (score v) {7*(i+1)} }};'))
        declarations = '\n'.join(rows) + '\n'
        # All instances are in scope at the two calls, including the unused middle ones.
        first = '(B0 y)' if n else 'y'
        last = f'(B{n-1} y)' if n else 'y'
        expression = ('let { ident a = a; b = ident (ltInt x 0); y = ident x } '
                      f'in if b then score {first} else score {last}')
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

    elif family == 'closed_field_projection':
        declarations = '''data Graph = Graph Int Int Int;
project :: Graph -> Int;
project graph = case graph of { Graph first second field -> field };
makeGraph :: Int -> Graph;
makeGraph x = if ltInt x 0 then Graph x (subInt x 1) (addInt (mulInt x 2) 1)
              else Graph (addInt x 1) x (addInt (mulInt x 3) 2);
'''
        if n == 0:
            entry = 'let { small = remInt value 11; graph = makeGraph small } in small'
        else:
            indices = range(1, n + 1)
            fields = [f'field{i}' for i in indices]
            types = ' '.join(['Int'] * n)
            pattern = ' '.join(fields)
            added = ' '.join(f'(addInt x {i})' for i in indices)
            subtracted = ' '.join(f'(subInt x {i})' for i in indices)
            terms = [f'addInt (project graph) {field}' for field in fields]
            total = balanced(terms, lambda a, b: f'addInt ({a}) ({b})')
            declarations += (f'data Inputs = Inputs {types};\n'
                             'makeInputs :: Int -> Inputs;\n'
                             f'makeInputs x = if ltInt x 0 then Inputs {added} else Inputs {subtracted};\n'
                             'score :: Graph -> Inputs -> Int;\n'
                             f'score graph inputs = case inputs of {{ Inputs {pattern} -> {total} }};\n')
            entry = 'let { small = remInt value 11 } in score (makeGraph small) (makeInputs small)'
        return HEADER + declarations + f'entry :: Int -> Int;\nentry value = {entry};\n' + MAIN
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


def cold_curried_library(n):
    header = HEADER.replace('module Main (main)', 'module CurryLibrary')
    rows = ['data Payload = Payload Int Int Int Int Int Int Int;',
            'data Job = Job (Int -> Int -> Int -> Int -> Int -> Int -> Payload);',
            'data Jobs = End | More Job Jobs;']
    for i in range(n):
        rows += [f'job{i} :: Job;', f'job{i} = Job (\\a -> \\b -> \\c -> \\d -> \\e -> \\f -> Payload {i+1} a b c d e f);']
    return header + '\n'.join(rows) + '\n}\n'


def cold_curried_job_list(n):
    prefix = cold_curried_library(0).removesuffix('\n}\n') + '\n'
    jobs = ''.join(f'More (Job (\\a -> \\b -> \\c -> \\d -> \\e -> \\f -> Payload {i+1} a b c d e f)) ('
                   for i in range(n)) + 'rest' + ')'*n
    return (prefix + f'jobs :: Jobs -> Jobs; jobs rest = {jobs};\n' +
            'allJobs :: Jobs; allJobs = jobs End\n}\n')


def cold_curried_facade():
    header = HEADER.replace('module Main (main)', 'module CurryFacade')
    return header + '''import CurryLibrary;
value :: Payload -> Int;
value (Payload tag a b c d e f) =
  addInt tag (addInt a (addInt (mulInt 2 b) (addInt (mulInt 3 c)
    (addInt (mulInt 4 d) (addInt (mulInt 5 e) (mulInt 6 f))))));
run :: Int -> Jobs -> Int;
run x End = 0;
run x (More (Job worker) rest) = let { saved = worker x (addInt x 1) } in
  addInt (value (saved (addInt x 2) (addInt x 3) (addInt x 4) (addInt x 5)))
    (addInt (value (saved (subInt x 4) (subInt x 9) (subInt x 16) (subInt x 25))) (run x rest))
}
'''


def expected(family, n, x):
    """Closed-form specifications; no compiled results or generated helpers used."""
    if family == 'module_string_literals':
        if not n:
            return x
        i = min(max(x, 0), n - 1)
        size, last = [(6, 101), (7, 101), (4, 108), (69, 120),
                      (62 + len(str(i)), 48 + i % 10)][i % 5]
        return size * 257 + last
    if family == 'mixed_unicode_literal':
        last = 16 * n + 1
        index = 0 if x < 0 else last if x == 0 else x % last
        code = ord('λ') if index == 0 else ord('界') if index == last else ord('a') + (index - 1) % 16
        return last + 1 + code
    if family == 'baseline':
        return x
    if family in ('polymorphic_import_spine', 'duplicated_type_arguments'):
        return x
    if family == 'closed_dictionary_result':
        total = x - n // 2 + (x + n - 1 if n % 2 else 0)
        return (total + 2**63) % 2**64 - 2**63
    if family in ('recursive_dictionary_forwarding', 'recursive_dictionary_alias'):
        # Each Box/Tag pair contributes -1. An unpaired Box contributes seed + n - 1.
        seed = x + 1
        total = seed - n // 2 + (seed + n - 1 if n % 2 else 0)
        return (total + 2**63) % 2**64 - 2**63
    if family in ('repeated_dictionary_arguments', 'bounded_dictionary_arguments'):
        return (x + n + 2**63) % 2**64 - 2**63
    if family == 'captured_parameter_uses':
        total = n*x + n*(n+1)//2
        return (total + 2**63) % 2**64 - 2**63
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
    if family in ('delayed_packet_fanout', 'retained_packet_dependency'):
        offsets = n*(n-1)//2
        if x == 0:
            return offsets
        right_count = min(n, max(0, x + 4))
        right_offsets = right_count*(right_count-1)//2
        return right_count*(3-x) + (n-right_count)*(x+3) + offsets - 2*right_offsets
    if family == 'wide_thunk_captures':
        offsets = n * (n + 1) // 2
        if x < 0:
            # Four adjacent products expand to 4*x^2 + 28*x + 68.
            return n * (4*x*x + 28*x + 68) + offsets
        return n*x - offsets
    if family == 'captured_thunk_fanout':
        if x < 0:
            return x*n*(n+1)//2 + n*(9-x)*(2*x+3)
        return n*(x*(x+3) + (2*x+3)*(9+x))
    if family == 'repeated_ground_dictionary_demands':
        turns, rest = divmod(n, 4)
        lengths = 10 * turns + rest * (rest + 1) // 2
        return 2 * (abs(x) + lengths) + (2 if x == 0 else 1)
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
    if family == 'nested_worker_applications':
        key = x % 11 if x >= 0 else -((-x) % 11)
        if key == 6:
            return 0
        odd, even = (n + 1) // 2, n // 2
        # Alternating flags make odd rows return 3 twice for a negative key.
        # For a nonnegative key their saved calls contribute the sum of odd indices.
        result = 9*odd + even*(even+1) if key < 0 else odd*key + 2*odd*odd + 3*even
        return (result + 2**63) % 2**64 - 2**63
    if family == 'recursive_lookup_workers':
        # Each stored key contributes once if its signed Int64 offset is visited.
        modulus = 2**64
        return sum(value for key, value in ((2, 17), (5, 41), (8, 73)) if (key - x) % modulus < n)
    if family == 'stable_recursive_workers':
        def remainder(number, divisor):
            return number % divisor if number >= 0 else -((-number) % divisor)

        # readInt and addInt operate on signed 64-bit words. Truncating
        # remainder keeps the sign of each input to the 24-argument function.
        score = 0
        for offset in range(3, 27):
            value = (x + offset + 2**63) % 2**64 - 2**63
            score = remainder(3*score + remainder(value, 31), 97)
        # Sum each recursion level across the table. Every 19 workers use
        # every residue exactly once, regardless of the starting position.
        cycles, rest = divmod(n, 19)
        total = n*(n+1)//2 + score
        for level in range(1, remainder(x, 11)+1):
            total += cycles*(18*19//2) + sum((level+i) % 19 for i in range(1, rest+1))
        return (total + 2**63) % 2**64 - 2**63
    if family in ('retained_curried_dependencies','retained_curried_job_list'):
        # Each tag is observed twice. The two weighted suffixes contribute
        # offsets 0, 4, -6, -24, -60 and -120 to each job.
        total = n * (42 * x - 206) + n * (n + 1)
        return (total + 2**63) % 2**64 - 2**63
    if family == 'escaping_curried_jobs':
        # The suffix offsets cancel in their original positions. Each endpoint
        # rotates the coefficients of the independently computed positional sum.
        total = n*(n-1)
        for endpoint in range(n):
            for position in range(12):
                field = (endpoint+position) % 12
                pair = 2*(x + field+1) if field < 8 else 2*x
                total += (1 << (11-position))*pair
        return (total + 2**63) % 2**64 - 2**63
    if family == 'captured_application_spines':
        if x < 0:
            total = n*x + sum(i % 12 for i in range(n)) + n*(n-1)//2
        else:
            total = n*x + sum((i-1) % 12 for i in range(n)) - n*(n-1)//2
        return (total + 2**63) % 2**64 - 2**63
    if family == 'curried_environment_prefix':
        linear = n*(n+1)//2
        quadratic = n*(n+1)*(2*n+1)//6
        total = 2*(x*linear + quadratic)
        return (total + 2**63) % 2**64 - 2**63
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
    if family == 'single_token_infix_sites':
        return x + n
    if family == 'nested_recursive_monad_peers':
        # Each of four peers takes n ticks plus one local tick. The peer
        # offsets add 1 + 2 + 3 + 4 during the complete circuit.
        return x + 4*n + 14
    if family == 'recursive_monad_peers':
        return x + 4*n + 10
    if family == 'local_recursive_checks':
        # The outer choices visit one complete ring. The three leaves are
        # two levels below the root, and the left choice falls back at depth one.
        count = max(n, 1)
        return x + 11 + n * (n - 1) // 2 + 3 * (2 % count) + 1 % count
    if family == 'checked_groups_then_dictionary':
        count = 4 * n
        arm = x % 12
        prefix = sum(x*(arm+1) + i + 2*arm+1 if x < i+arm else x+3*arm+2-i for i in range(count)) if count else x
        return prefix + n * (n + 1) // 2 + 2 * n
    if family in ('local_monadic_dictionary_uses', 'ground_monadic_dictionary_uses'):
        return x + n*(n+1)//2 + 2*n
    if family == 'inferred_monadic_recursion':
        return ((n + 1)*x + 2**63) % 2**64 - 2**63
    if family == 'bounded_optional_writers':
        offsets = n * (n - 1) // 2
        if x < 0:
            return 10 * n + offsets
        def wrap(i):
            return (i + 2**63) % 2**64 - 2**63
        return offsets + 6*n + sum(len(str(wrap(x+i))) for i in range(n))
    if family == 'inferred_constructor_writers':
        count = n * (n + 1) // 2
        offsets = count - n
        value = (x * count + offsets) if x > 0 else (-n * x - offsets) if x < 0 else -count
        return (value + 2**63) % 2**64 - 2**63
    if family == 'mixed_recursive_decoder':
        if x < 0:
            return 7
        if x >= n:
            return -37
        return (x + 2) ** 2 + 10
    if family == 'signed_decoder_selectors':
        if x < 0 or x >= n:
            return -99
        return -11 if x == 0 else (x + 2) * (x + 1) + 2 * x - 1
    if family == 'shared_callback_let_chain':
        computed = max(0, min(n, x+1))
        magnitude = abs(x) * pow(abs(x+2), computed, 251) * pow(abs(x+1), n-computed, 251) % 251
        return -magnitude if x < 0 and n % 2 == 0 else magnitude
    if family == 'queued_callback_let_chain':
        value = (n+1)*x + max(0, min(n, x+1))
        return -(abs(value) % 251) if value < 0 else value % 251
    if family == 'deferred_constructor_spine':
        return 0 if x < 0 else x+n-1
    if family == 'checked_constructor_dispatch':
        steps = min(max(x, 0), n)
        return (steps + 1) * (2*x - steps) // 2
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
    if family == 'visible_instance_inventory':
        selected = min(1, n) if x < 0 else n
        return (x + 7*selected + 2**63) % 2**64 - 2**63
    if family == 'class_instances':
        return x*n*(n+1)//2 + n*(n-1)*(n+1)//3
    if family == 'dependency_diamonds':
        change = n*(n+1)//2
        return x + change if x < 0 else x - change
    if family == 'captured_closures':
        return x * n * (n + 1) // 2 - n * (n + 1) * (2 * n + 1) // 6
    if family == 'closed_field_projection':
        small = -(abs(x) % 11) if x < 0 else x % 11
        if n == 0:
            return small
        offsets = n * (n + 1) // 2
        return n * (3 * small + 1) + offsets if small < 0 else n * (4 * small + 2) - offsets
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


def generate(out, sizes=None, families=None, baseline_family=None):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    cells = coordinates(sizes, families)
    if baseline_family is not None and (
        not REGISTRY['families'].get(baseline_family, {}).get('matched_zero') or
        {family for family, _ in cells} != {'baseline', baseline_family}
    ):
        raise ValueError('a matched baseline requires the zero cell and exactly its growing family')
    cases = []
    for family, n in cells:
        source_family = baseline_family if family == 'baseline' and baseline_family else family
        identity = f'{family}-{n}'
        directory = out/identity; directory.mkdir()
        source = directory/'Main.hs'; source.write_text(program(source_family,n))
        inputs = [-1,0,n+3] if family == 'recursive_ring' else [-1,0,7]
        if family == 'module_string_literals':
            inputs = list(dict.fromkeys([-1, 0, 1, 2, 3, 4, n//2, n-1, n+1]))
        elif family == 'wide_case':
            inputs = [-1, n//2, n, '--all']
        elif family == 'visible_instance_inventory':
            inputs = [-2**63, -1, 0, 7, 2**63-1]
        elif family == 'closed_field_projection':
            inputs = [-2**63, -57, -1, 0, 1, 7, 12, 2**63-1]
        elif family == 'nested_worker_applications':
            inputs = [-2**63, -7, -1, 0, 6, 7, 17, 2**63-1]
        elif family == 'recursive_lookup_workers':
            inputs = [3 - n, 5 - n//2, 8, 9]
        elif family == 'decoder_pipeline':
            inputs = data_shapes.inputs(family, n)
        elif family == 'rank2_callbacks':
            inputs = [-1, n//2, n]
        elif family == 'inferred_dictionary_prefix':
            inputs = [-n-1, -n, n-1]
        elif family == 'checked_constructor_dispatch':
            inputs = [-1, 0, n//2, 2*n+3]
        elif source_family == 'bounded_optional_writers':
            inputs = [-9, 0, 9, 99, 2**63-1]
        elif source_family == 'inferred_constructor_writers':
            inputs = [-9, -1, 0, 3, 17]
        elif source_family == 'mixed_recursive_decoder':
            inputs = [-5, 0, n//2, n-1, n+2] if n >= 3 else [-5, -1, 0, 1, 2]
        elif source_family == 'signed_decoder_selectors':
            inputs = [-1, 0, n//2, n-1, n+1] if n >= 3 else [-2, -1, 0, 1, 7]
        elif family == 'mixed_parser_recursion':
            inputs = [-1, 0, n-1, n, 2*n+1]
        elif family == 'local_dictionary_branch_fanout':
            limit = n*(n+1)//2 + 1
            inputs = [-limit, 0, limit]
        elif family in ('shared_callback_let_chain', 'queued_callback_let_chain'):
            inputs = [1, 7, 19]
        elif family in ('captured_closures', 'wide_product'):
            inputs = [-n-1, 0, n+1]
        case = {'id':identity,'family':family,'size':n,'source':str(source.resolve()),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_bytes':source.stat().st_size,
            'inputs':inputs, 'expected_stdout':[expected_output(source_family,n,x) for x in inputs],
            'syntax':'shared-haskell-v1; identical source bytes for GHC and MLF',
            'route':'one Main module, imports fixed MLF.Primitive; main reads runtime argv'}
        if family == 'retained_packet_dependency':
            library=directory/'PacketLibrary.hs'
            library.write_text(HEADER.replace('module Main (main)', 'module PacketLibrary') +
                               packet_declarations(n) + '}\n')
            case.update(dependency={'source':str(library.resolve()),
                         'module':'PacketLibrary','sha256':hashlib.sha256(library.read_bytes()).hexdigest()},
                        route='PacketLibrary and Main both start from source')
        if source_family in ('retained_curried_dependencies','retained_curried_job_list'):
            library = (cold_curried_job_list(n) if source_family == 'retained_curried_job_list'
                       else cold_curried_library(n))
            sources = [('CurryLibrary', library), ('CurryFacade', cold_curried_facade())]
            dependencies = []
            for module, contents in sources:
                dep = directory/(module+'.hs')
                dep.write_text(contents)
                dependencies.append({'source':str(dep.resolve()),'module':module,
                                     'sha256':hashlib.sha256(dep.read_bytes()).hexdigest()})
            case.update(dependencies=dependencies,
                        route='CurryLibrary, CurryFacade and Main all start from source')
        if source_family != family:
            case['matched_baseline_for'] = source_family
        cases.append(case)
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    return cases
