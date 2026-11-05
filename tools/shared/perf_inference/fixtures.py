from pathlib import Path
import sys
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
def lets(n,expr):return ''.join(f'let v{i} = {expr} in ' for i in range(n))
fixtures={
 'control':('int',lets(8,'(\\x -> x) 1')+'42'),
 'class-empty':('int','class Inspect a where { inspect : a -> Bool }; '+lets(8,'(\\x -> x) 1')+'42'),
 'class-ordinary':('bool','class Inspect a where { inspect : a -> Bool }; instance Inspect Int where { inspect = \\x -> true }; '+lets(8,'inspect 1')+'inspect 42'),
 'class-recursive':('bool','class Inspect a where { inspect : a -> Bool }; instance Inspect Int where { inspect = \\x -> true }; let rec { f x = if true then inspect x else f x } in '+lets(8,'f 1')+'f 42'),
 'field-known':('int','data Box a = Box a; case (Box (\\x -> x) :: Box (forall a. a -> a)) of { Box f -> '+lets(8,'f true')+'f 42 }'),
 'field-unknown':('int','data Box a = Box a; case Box (\\x -> x) of { Box f -> '+lets(8,'f 1')+'f 42 }'),
 'field-canonical':('int','data Value = Value Int; case Value 42 of { Value x -> x }'),
 'field-raw':('int','data Value = Value (forall a. Int); case Value 42 of { Value x -> x }'),
 'class-canonical':('int','class Value a where { value : a -> Int }; instance Value Bool where { value = \\x -> 42 }; value true'),
 'class-raw':('int','class Value a where { value : forall unused. a -> Int }; instance Value Bool where { value = \\x -> 42 }; value true'),
}
for name,(kind,src) in fixtures.items():(out/(name+'.emlf')).write_text(src+'\n')
import json
(out/'index.json').write_text(json.dumps({n:k for n,(k,s) in fixtures.items()},indent=2))
