"""Pure fixtures only. Never runs a compiler, interpreter, host or native binary."""
import copy
import unittest
import utf8_batch_contract as B

ORIGINAL = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,\n             KindSignatures, FlexibleContexts, FlexibleInstances,\n             MultiParamTypeClasses, OverloadedStrings #-}\nmodule Main where {\n  import MLF.Primitive;\n  import Bootstrap.Types;\n  import qualified Bootstrap.Std as S;\n  emit text = do { printInt (stringUtf8Length text); printInt (stringLength text) };\n  main = do {\n    mode <- getArg 0;\n    if eqString mode \"argument\" then emit (panic \"text-first\")\n    else if eqString mode \"invalid\" then emit (stringFromCode 55296)\n    else if eqString mode \"unused\" then printInt (if True then 42 else stringUtf8Length (panic \"unused\"))\n    else if eqString mode \"scalar\" then do { value <- getArg 1; emit (stringFromCode (readInt value)) }\n    else do {\n      value <- getArg 1;\n      let { text = S.concatStrings (S.replicate (readInt value) (\"aα中😀\" ++ stringFromCode 0)) };\n      if eqString mode \"slice\" then do {\n        start <- getArg 2; count <- getArg 3;\n        emit (stringSlice text (readInt start) (readInt count))\n      } else emit text\n    }\n  }\n}\n".encode('utf-8')
# Independent literal expected lengths, not computed by B.vectors/generate/parse.
EXPECTED = {
 0:(0,0),1:(11,5),2:(22,10),3:(693,315),4:(704,320),5:(715,325),
 10:(1,1),11:(1,1),12:(1,1),13:(2,1),14:(2,1),15:(3,1),
 16:(3,1),17:(3,1),18:(3,1),19:(4,1),20:(4,1),
 21:(0,0),22:(11,5),23:(9,3),24:(16,7),25:(1,1),26:(9,3),27:(1,1),28:(0,0)}
IDS = (0,1,2,3,4,5,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28)

def raw(direction='forward'):
    order = IDS if direction == 'forward' else tuple(reversed(IDS))
    return b''.join(('%d\n%d\n%d\n%d\n%d\n' %
                    (812340001,i,*EXPECTED[i],812340002)).encode() for i in order)

def baseline():
    return {i:('%d\n%d\n'%EXPECTED[i]).encode() for i in IDS}

def evidence():
    physical=[]; logical=[]
    for lane in ('host','interpreter'):
        for direction in ('forward','reverse'):
            capture=raw(direction)
            p=B.physical_record(lane+'-'+direction,lane,direction,['fixture'],capture,b'',0)
            physical.append(p)
            for i in IDS:
                argv=['original-fixture','--']+list(B.vectors()[i]['arguments'])
                logical.append(B.project(p,capture,i,argv,baseline()[i]))
    return physical,logical,baseline()

class ContractTests(unittest.TestCase):
    def test_fixed_source_identity_and_all_body_bytes(self):
        self.assertEqual(B.FIXTURE_BLOB,'dcef64296a26296b720d0ffa00016d808f7cee1e')
        self.assertEqual(B.FIXTURE_PATH,'tools/shared/fixtures/utf8-length/Length.hs')
        for d in ('forward','reverse'):
            generated=B.generate(ORIGINAL,d)
            self.assertEqual(B.restore(generated,d),ORIGINAL)
            body=ORIGINAL.replace(b'  main = do {\n',b'  runCase getArg = do {\n')[:-2]
            self.assertTrue(generated.startswith(body))
            self.assertEqual(generated.count(b'    runCase (\\index -> '),25)
            self.assertIn(b'panic "UTF8 batch getArg out of range"',generated)
            self.assertIn(b'if eqInt index 0 then ioReturn',generated)
            self.assertIn(b'if eqInt index 3 then ioReturn',generated)

    def test_source_and_inverse_corruption(self):
        for changed in (ORIGINAL+b' ',ORIGINAL.replace(b'emit text',b'emit changed'),
                        ORIGINAL.replace(b'  main = do {',b'  other = do {')):
            with self.assertRaises(ValueError): B.generate(changed,'forward')
        g=B.generate(ORIGINAL,'forward')
        for changed in (g+b' ',g.replace(b'printInt 812340001',b'printInt 812340003',1),
                        g.replace(b'runCase getArg',b'runCase bad',1)):
            with self.assertRaises(ValueError): B.restore(changed,'forward')
        with self.assertRaises(ValueError): B.restore(g,'reverse')
        with self.assertRaises(ValueError): B.generate(ORIGINAL,'unknown')

    def test_literal_inventory_and_expected_values(self):
        self.assertEqual(B.FORWARD,IDS)
        self.assertEqual(B.REVERSE,tuple(reversed(IDS)))
        self.assertEqual({i:r['expected'] for i,r in B.vectors().items()},EXPECTED)
        self.assertEqual(B.vectors()[5]['arguments'],('count','65'))
        self.assertEqual(B.vectors()[10]['arguments'],('scalar','0'))
        self.assertEqual(B.vectors()[28]['arguments'],('slice','65','325','0'))

    def test_both_directions_actual_ranges(self):
        for d in ('forward','reverse'):
            capture=raw(d); rows=B.parse(capture,d)
            self.assertEqual([r['index'] for r in rows],list(IDS if d=='forward' else reversed(IDS)))
            for r in rows:
                self.assertEqual(capture[r['start']:r['end']],baseline()[r['index']])
                self.assertEqual(r['actual_ascii'].encode(),baseline()[r['index']])

    def test_output_negative_matrix(self):
        good=raw(); lines=good.splitlines(keepends=True)
        variants=[good[:-1],good+b'0\n',good.replace(b'812340001',b'812340003',1),
                  raw('reverse'),b''.join(lines[:5]+lines[:5]+lines[10:])]
        for badnum in (b'+0',b'-0',b'00',b' 0',b'0 ',b'0\r',b'9223372036854775808',
                       b'99999999999999999999',b'\xff'):
            changed=list(lines);changed[2]=badnum+b'\n';variants.append(b''.join(changed))
        changed=list(lines);changed[2]=b'1\n';variants.append(b''.join(changed))
        changed=list(lines);changed[1]=b'29\n';variants.append(b''.join(changed))
        for bad in variants:
            with self.subTest(bad=bad[:40]),self.assertRaises(ValueError): B.parse(bad,'forward')
        with self.assertRaises(ValueError): B.parse(b'x'*32769,'forward')

    def test_physical_failure_never_yields_projections(self):
        for status,err in ((1,b''),(0,b'warning'),(True,b'')):
            with self.assertRaises(ValueError):
                B.physical_record('id','interpreter','forward',['fixture'],raw(),err,status)

    def test_projection_checks_real_bytes_and_original_expectation(self):
        p=B.physical_record('id','interpreter','forward',['fixture'],raw(),b'',0)
        argv=['emlf','--run','original','--','count','0']
        row=B.project(p,raw(),0,argv,b'0\n0\n')
        self.assertFalse(row['fresh_process'])
        self.assertNotIn('exit_code',row)
        self.assertNotIn('seconds',row)
        for capture,index,args,expect in ((raw()+b'0\n',0,argv,b'0\n0\n'),
             (raw(),6,argv,b'0\n0\n'),(raw(),0,argv[:-1]+['1'],b'0\n0\n'),
             (raw(),0,argv,b'1\n0\n')):
            with self.assertRaises(ValueError): B.project(p,capture,index,args,expect)
        p['vectors'][0]['start']+=1
        with self.assertRaises(ValueError): B.project(p,raw(),0,argv,b'0\n0\n')

    def test_four_batches_all_projections_and_host_comparison(self):
        p,l,h=evidence()
        r=B.aggregate(p,l,h)
        self.assertTrue(r['batch_complete'])
        self.assertFalse(r['whole_utf8_complete'])
        self.assertFalse(r['original_fresh_demand_gate_complete'])
        for pp,ll,hh in ((p[:-1],l,h),(p,l[:-1],h),(p,l+[l[0]],h),(p,l,{0:b'0\n0\n'})):
            with self.assertRaises(ValueError): B.aggregate(pp,ll,hh)
        for field,value in (('fresh_process',True),('actual_ascii','99\n0\n'),
                            ('start',999),('physical_stdout_sha256','wrong')):
            rows=copy.deepcopy(l);rows[0][field]=value
            with self.assertRaises(ValueError): B.aggregate(p,rows,h)
        rows=copy.deepcopy(l);rows[1]=copy.deepcopy(rows[0])
        with self.assertRaises(ValueError): B.aggregate(p,rows,h)
        pp=copy.deepcopy(p);pp[1]['direction']='forward'
        with self.assertRaises(ValueError): B.aggregate(pp,l,h)
        hh=dict(h);hh[0]=b'1\n0\n'
        with self.assertRaises(ValueError): B.aggregate(p,l,hh)

    def test_coordinated_physical_logical_and_host_corruption(self):
        p,l,h=evidence()
        for physical in p:
            physical['vectors'][0]['actual_ascii']='99\n0\n'
            physical['vectors'][0]['actual_sha256']=B.digest(b'99\n0\n')
        for logical in l:
            physical=next(x for x in p if x['id']==logical['physical_command_id'])
            if logical['index']==physical['vectors'][0]['index']:
                logical['actual_ascii']='99\n0\n'
                logical['actual_sha256']=B.digest(b'99\n0\n')
                h[logical['index']]=b'99\n0\n'
        with self.assertRaisesRegex(ValueError,'independent expected/hash'):
            B.aggregate(p,l,h)

    def test_bool_and_coordinated_offset_corruption(self):
        p,l,h=evidence()
        for field in ('index','start','end'):
            pp=copy.deepcopy(p);pp[0]['vectors'][0][field]=False
            with self.assertRaises(ValueError): B.aggregate(pp,l,h)
            ll=copy.deepcopy(l);ll[0][field]=False
            with self.assertRaises(ValueError): B.aggregate(p,ll,h)
        pp=copy.deepcopy(p);pp[0]['stdout_bytes']=True
        with self.assertRaises(ValueError): B.aggregate(pp,l,h)
        pp=copy.deepcopy(p);ll=copy.deepcopy(l)
        pp[0]['vectors'][0]['start']+=1
        ll[0]['start']+=1
        with self.assertRaisesRegex(ValueError,'offset/range'): B.aggregate(pp,ll,h)
        pp=copy.deepcopy(p);pp[0]['vectors'][0]['actual_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'independent expected/hash'): B.aggregate(pp,l,h)
        with self.assertRaises(ValueError):
            B.project(p[0],raw(),False,['fixture','count','0'],b'0\n0\n')


class MonomorphicLoopControls(unittest.TestCase):
    # Independent literal input inventory, not copied from B.vectors at runtime.
    arguments = (
        (0, ('count','0')), (1, ('count','1')), (2, ('count','2')),
        (3, ('count','63')), (4, ('count','64')), (5, ('count','65')),
        (10, ('scalar','0')), (11, ('scalar','1')), (12, ('scalar','127')),
        (13, ('scalar','128')), (14, ('scalar','2047')), (15, ('scalar','2048')),
        (16, ('scalar','55295')), (17, ('scalar','57344')), (18, ('scalar','65535')),
        (19, ('scalar','65536')), (20, ('scalar','1114111')),
        (21, ('slice','65','0','0')), (22, ('slice','65','0','5')),
        (23, ('slice','65','1','3')), (24, ('slice','65','3','7')),
        (25, ('slice','65','255','1')), (26, ('slice','65','256','3')),
        (27, ('slice','65','324','1')), (28, ('slice','65','325','0')))

    def test_whole_original_inverse_and_single_call_site(self):
        header = (b'  runCase :: (Int -> IO String) -> IO ();\n'
                  b'  runCase getArg = do {\n')
        for direction in ('forward','reverse'):
            generated = B.generate_loop(ORIGINAL, direction)
            self.assertEqual(B.restore_loop(generated, direction), ORIGINAL)
            self.assertTrue(generated.startswith(ORIGINAL.replace(b'  main = do {\n', header, 1)[:-2]))
            self.assertEqual(generated.count(b'runCase (batchArgument args);'), 1)
            self.assertEqual(generated.count(b'printInt 812340001;'), 1)
            self.assertEqual(generated.count(b'printInt 812340002;'), 1)
            self.assertNotIn(b'runCase (\\index ->', generated)
            for signature in (header.splitlines()[0],
                b'  batchArgument :: [] String -> Int -> IO String;',
                b'  batchLoop :: [] ((,) Int ([] String)) -> IO ();',
                b'  batchCases :: [] ((,) Int ([] String));', b'  main :: IO ();'):
                self.assertEqual(generated.count(signature), 1)
            self.assertIn(b'if ltInt index 0 then panic "UTF8 batch getArg out of range"', generated)
            self.assertIn(b'[] -> panic "UTF8 batch getArg out of range"', generated)
            self.assertIn(b'if eqInt index 0 then ioReturn value', generated)
            self.assertIn(b'else batchArgument rest (subInt index 1)', generated)
            self.assertIn(b'[] -> ioReturn ();', generated)

    def test_independent_literal_table_is_complete_and_exactly_ordered(self):
        self.assertEqual(tuple(index for index, _ in self.arguments), IDS)
        self.assertEqual(len({index for index, _ in self.arguments}), 25)
        for direction in ('forward','reverse'):
            entries = self.arguments if direction == 'forward' else tuple(reversed(self.arguments))
            wanted = ('  batchCases = [' + ', '.join(
                '(,) %d [%s]' % (index, ', '.join('"%s"' % arg for arg in args))
                for index, args in entries) + '];').encode('ascii')
            generated = B.generate_loop(ORIGINAL, direction)
            actual = [line for line in generated.splitlines() if line.startswith(b'  batchCases = ')]
            self.assertEqual(actual, [wanted])

    def test_loop_source_tail_signature_and_inventory_changes_fail_closed(self):
        generated = B.generate_loop(ORIGINAL, 'forward')
        replacements = (
            (b'runCase getArg', b'runCase bad'),
            (b'emit text', b'emit changed'),
            (b'Int -> IO String', b'Int -> IO Int'),
            (b'runCase (batchArgument args);', b'ioReturn ();'),
            (b'printInt 812340001', b'printInt 812340003'),
            (b'(,) 0 ["count", "0"], ', b''),
            (b'(,) 0 ["count", "0"]', b'(,) 0 ["count", "0"], (,) 0 ["count", "0"]'),
            (b'(,) 28 ["slice", "65", "325", "0"]', b'(,) 28 ["slice", "65", "325", "1"]'))
        for before, after in replacements:
            self.assertIn(before, generated)
            changed = generated.replace(before, after, 1)
            with self.subTest(before=before), self.assertRaises(ValueError):
                B.restore_loop(changed, 'forward')
        for changed in (generated+b' ', generated[:-1]):
            with self.assertRaises(ValueError): B.restore_loop(changed, 'forward')
        with self.assertRaises(ValueError): B.restore_loop(generated, 'reverse')
        with self.assertRaises(ValueError): B.generate_loop(ORIGINAL, 'unknown')
        with self.assertRaises(ValueError): B.generate_loop(ORIGINAL+b' ', 'forward')

    def test_legacy_and_loop_domains_do_not_silently_substitute(self):
        for direction in ('forward','reverse'):
            legacy = B.generate(ORIGINAL, direction)
            loop = B.generate_loop(ORIGINAL, direction)
            self.assertEqual(B.restore(legacy, direction), ORIGINAL)
            self.assertEqual(B.restore_loop(loop, direction), ORIGINAL)
            self.assertEqual(legacy.count(b'    runCase (\\index -> '), 25)
            with self.assertRaises(ValueError): B.restore_loop(legacy, direction)
            with self.assertRaises(ValueError): B.restore(loop, direction)

if __name__=='__main__':
    unittest.main()
