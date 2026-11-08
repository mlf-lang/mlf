import unittest,random,hashlib,struct
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/shared"))
import artifact_binary_reference as g
import packed_writer_candidate as f
class Diff(unittest.TestCase):
 def sequence(self,seq):
  a,b=g.Writer(),f.Writer()
  for value,width in seq:
   a.put(value,width);b.put(value,width);self.assertEqual(a.bytes(),b.bytes());self.assertEqual(b.bytes(),b.bytes())
  snap=b.bytes();a.put(173,8);b.put(173,8);self.assertEqual(a.bytes(),b.bytes());self.assertEqual(snap,b.bytes()[:len(snap)] if sum(w for _,w in seq)%8==0 else snap)
 def test_exhaust_small_values_offsets(self):
  for offset in range(8):
   for width in range(10):
    for v in range(1<<width):self.sequence([(0,offset),(v,width)])
 def test_wide_crossings(self):
  rng=random.Random(9341)
  for _ in range(300):
   seq=[]
   for n in [0,1,7,8,9,15,16,31,32,63,64]:seq.append((rng.randrange(1<<n),n))
   self.sequence(seq)
 def test_varuint(self):
  for v in [0,1,127,128,129,(1<<64)-1]+[x for k in range(1,64) for x in [(1<<k)-1,1<<k]]:
   a,b=g.Writer(),f.Writer();a.put(3,2);b.put(3,2);a.varuint(v);b.varuint(v);self.assertEqual(a.bytes(),b.bytes())
 def test_range_errors(self):
  for method,args in [('put',(-1,8)),('put',(256,8)),('put',(1,0)),('put',(0,-1)),('varuint',(-1,)),('varuint',(1<<64,))]:
   errors=[]
   for mod in [g,f]:
    try:getattr(mod.Writer(),method)(*args)
    except Exception as e:errors.append((type(e).__name__,str(e)))
   self.assertEqual(len(errors),2);self.assertEqual(*errors)
 def test_mutable_bits_compatibility(self):
  a,b=g.Writer(),f.Writer();a.put(3,2);b.put(3,2);self.assertEqual(a.bits,b.bits)
  for x in [a,b]:x.bits.extend([1,0,1]);x.bits[0]=0;x.put(29,5)
  self.assertEqual(a.bits,b.bits);self.assertEqual(a.bytes(),b.bytes())
  for x in [a,b]:x.bits=[1,1,0];x.put(3,2)
  self.assertEqual(a.bytes(),b.bytes())
 def documents(self,symbols,nodes,roots,schema,**kw):
  a=g.explicit_document(symbols,nodes,roots,schema,**kw);b=f.explicit_document(symbols,nodes,roots,schema,**kw);self.assertEqual(a,b)
  self.assertEqual(a[:8],g.MAGIC);self.assertEqual(g.repair_crc(a),f.repair_crc(b))
  outcomes=[]
  for mod,raw in [(g,a),(f,b)]:
   try:d=mod.read_document(raw,schema);outcomes.append(('ok',d.values(),d.accounting()))
   except Exception as e:outcomes.append((type(e).__name__,str(e)))
  self.assertEqual(outcomes[0],outcomes[1])
 def test_explicit_all_kinds_and_malformed(self):
  for schema in [3,4,6,7]:
   self.documents(['','a\0b','é','漢','😀'],[(0,-(1<<63)),(0,(1<<63)-1),(1,0x8000000000000000),(1,0x7ff8000000000001),(2,3),(3,(9,(0,1,2,3,4)))],[5,0,5],schema)
   for args in [([],[],[]),(['x','x'],[(2,0)],[0]),([b'\xff'],[(2,0)],[0]),([],[(3,(1,(0,)))],[0]),([],[(0,1),(0,1)],[1]),([],[(0,0)],[0,0])]:self.documents(*args,schema)
   self.documents(['x'],[(2,0)],[0],schema,node_width=3,symbol_width=2)
 def test_trees_dag_roots_and_widths(self):
  rng=random.Random(19)
  for schema in [3,4,6,7]:
   for size in [0,1,2,3,7,8,9,31,32,33,63,64,65]:
    leaves=[('text','t'+str(i)+'\0é') for i in range(size)];shared=('node',17,tuple(leaves));roots=[shared,shared,('node',1,(shared,('int',-(1<<63)),('bits',0xffffffffffffffff)))]
    a=g.tree_document(roots,schema);b=f.tree_document(roots,schema);self.assertEqual(a,b)
   for _ in range(100):
    pool=[('int',rng.randint(-100000,100000)),('text','x\0😀'),('bits',rng.getrandbits(64))]
    for i in range(15):pool.append(('node',rng.randrange(500),tuple(rng.choice(pool) for _ in range(rng.randrange(5)))))
    roots=[pool[-1],pool[-3]];self.assertEqual(g.tree_document(roots,schema),f.tree_document(roots,schema))
 def test_parser_mutation_equivalence(self):
  raw=g.tree_document([('node',10,(('int',3),('text','xyz')))],6)
  for i in range(len(raw)):
   changed=bytearray(raw);changed[i]^=128
   for b in [bytes(changed),g.repair_crc(changed)]:
    results=[]
    for mod in [g,f]:
     try:d=mod.read_document(b,6);results.append(('ok',d.values()))
     except Exception as e:results.append((type(e).__name__,str(e)))
    self.assertEqual(*results)
 def test_nonwriter_source_exact(self):
  from pathlib import Path
  a=Path(g.__file__).read_text();b=Path(f.__file__).read_text();self.assertEqual(a[:a.index('class Writer:')],b[:b.index('class Writer:')]);self.assertEqual(a[a.index('\ndef repair_crc'):],b[b.index('\ndef repair_crc'):]);self.assertEqual(g.Limits().__dict__,f.Limits().__dict__)


class Independent(unittest.TestCase):
 def test_exact_pins(self):
  self.assertEqual(hashlib.sha256(Path(g.__file__).read_bytes()).hexdigest(), "de312e3415eba178b649d30b6fa2b113fc864455de16603a5902af034d036422")
  self.assertEqual(hashlib.sha256(Path(f.__file__).read_bytes()).hexdigest(), "fa5daa6fd8072825268d2045f1980d0a4bd141e5c79d34f0c90008251860003f")
  self.assertIsNot(g.Writer, f.Writer)
 def test_integer_oracle(self):
  rng=random.Random(9999)
  for offset in range(8):
   a=f.Writer();aggregate=0;length=0
   for width in [offset,0,1,6,7,8,9,63,64,65,127,128,129,255,256]*4:
    value=rng.getrandbits(width);a.put(value,width);aggregate|=value<<length;length+=width
    expected=aggregate.to_bytes((length+7)//8,'little');self.assertEqual(a.bytes(),expected);self.assertEqual(a.bytes(),expected)
 def test_fallback_alias_clear_and_reassign(self):
  a,b=g.Writer(),f.Writer()
  for x in [a,b]:x.put(0x155,9)
  av,bv=a.bits,b.bits;self.assertIs(bv,b.bits)
  for bits in [av,bv]:bits[1:4]=[1,1];bits.reverse();bits.append(0)
  for x in [a,b]:x.put(65535,16)
  self.assertEqual(a.bytes(),b.bytes());av.clear();bv.clear()
  for x in [a,b]:x.put(3,2)
  self.assertEqual(a.bytes(),b.bytes());self.assertEqual(a.bits,b.bits)
  for x in [a,b]:x.bits=[];x.varuint(300)
  self.assertEqual(a.bytes(),b.bytes())
 def test_invalid_range_no_state_change(self):
  for args in [(-1,1),(2,1),(1,0),(0,-1)]:
   a,b=g.Writer(),f.Writer()
   for x in [a,b]:x.put(7,3)
   errors=[]
   for x in [a,b]:
    try:x.put(*args)
    except Exception as exc:errors.append((type(exc).__name__,str(exc)))
   self.assertEqual(len(errors),2);self.assertEqual(*errors);self.assertEqual(a.bytes(),b.bytes())


if __name__ == "__main__":
 unittest.main()
