"""Literal legacy inputs/oracles and an array-backed numeric-region workload."""
import json,re
from pathlib import Path
TRIPLE=r'\(\(,,\)\s+("(?:\\.|[^"\\])*")\s+("(?:\\.|[^"\\])*")\s+("(?:\\.|[^"\\])*")'
def cases(root):
 text=(Path(root)/'tests/Tests/NumericArrays.emlf').read_text()
 start=text.index('\nprograms =');middle=text.index('\nfailures :',start)
 sections=[(False,text[start:middle],17),(True,text[text.index('\nfailures =',middle):],26)]
 result=[]
 for failure,section,count in sections:
  rows=[tuple(json.loads(v) for v in row) for row in re.findall(TRIPLE,section)]
  if len(rows)!=count:raise ValueError('legacy literal-case inventory changed')
  for label,source,expected in rows:
   if failure:source='do { putStrLn "before"; '+source+' }'
   result.append({'label':label,'source':source,'expected':expected,'failure':failure})
 return result

def region_program(root):
 # Preserve the existing fixture's recursive-function encoding. The expected
 # results come from separate Data.Int.Int64 code, never from these emitters.
 text=(Path(root)/'tests/Tests/NumericArrays.emlf').read_text()
 recursion=json.loads(re.search(r'\nrecursion = ("(?:\\.|[^"\\])*")',text).group(1))
 limit=2**62;maximum=2**63-1
 values=[-maximum,-limit-1,-limit,-3,0,3,limit-1,limit,maximum]
 pairs=[(a,b) for a in values for b in [-1,2,limit-1]]
 operations=['mulInt x y','quotInt x (-1)','remInt x (-1)','quotInt x 3','remInt x 3','quotInt x (-3)','remInt x (-3)','andInt x y']
 writes=''.join(f'writeIntArray b (addInt (mulInt i 8) {j}) ({op}); ' for j,op in enumerate(operations))
 source=recursion+f'let loop : IntArray -> IntArray -> Int -> IO Int = fix (\\again a b i -> ifThenElse (ltInt i {len(pairs)}) (do {{ x <- readIntArray a (mulInt i 2); y <- readIntArray a (addInt (mulInt i 2) 1); '+writes+'again a b (addInt i 1) }) (return 0)) in '
 source+=f'let dump : IntArray -> Int -> IO Int = fix (\\again a i -> ifThenElse (ltInt i {len(pairs)*8}) (do {{ x <- readIntArray a i; printInt x; again a (addInt i 1) }}) (return 0)) in '
 source+=f'do {{ a <- newIntArray {len(pairs)*2} 0; b <- newIntArray {len(pairs)*8} 0; '
 for index,(a,b) in enumerate(pairs):source+=f'writeIntArray a {index*2} ({a}); writeIntArray a {index*2+1} ({b}); '
 return source+'loop a b 0; dump b 0; printInt (remInt (readInt "-9223372036854775808") (-1)) }\n'

def minimum_regions(root):
 text=(Path(root)/'tests/Tests/NumericArrays.emlf').read_text()
 recursion=json.loads(re.search(r'\nrecursion = ("(?:\\.|[^"\\])*")',text).group(1))
 for op,failure,expected in [('quotInt',True,'integer division overflow'),('remInt',False,'before\n0\n')]:
  source=recursion+'let loop : IntArray -> IntArray -> Int -> IO Int = fix (\\again a b i -> ifThenElse (ltInt i 2) (do { x <- readIntArray a i; writeIntArray b i ('+op+' x (-1)); again a b (addInt i 1) }) (return 0)) in '
  source+='do { a <- newIntArray 2 (-9223372036854775808); b <- newIntArray 2 0; putStrLn "before"; loop a b 0; x <- readIntArray b 0; printInt x }\n'
  yield {'label':'numeric region minBound '+op,'source':source,'expected':expected,'failure':failure,'region':True}
