#!/usr/bin/env python3
"""Small independent comparator controls. Native-proof failures also run in CI.

Synthetic checksums/receipts below stand for the required native-helper
precondition. They do not purport to be native-admitted artifacts.
"""
import copy
import hashlib
import unittest
import open_file_comparison as C

N, S, L = C.node, C.string, C.sequence
I = lambda value: ('int', value)
X = lambda identity, hint: N(31, I(identity), S(hint))
TY = N(44, S('Int'), L([]))
UNIT = N(82, S('()'), L([]))

def iface(checksum):
    data = N(26, S('Box'), L([S('a')]), L([N(25, S('Box'), L([N(20, S('a'))]))]))
    return N(242, S('fixture'), L([]), L([S('Main')]), L([]), L([]),
             L([]), L([]), L([]), L([data]),
             L([N(2, S('main'), TY), N(2, S('unused'), TY)]),
             S('main'), S(checksum), L([]))

def linked(one=101, two=102):
    return N(84, L([]), N(75, X(one, 'main'), N(77, I(7)),
                 N(75, X(two, 'unused'), N(70, X(one, 'main')), N(70, X(one, 'main')))))

def fixture():
    ci = iface('native-vetted-closed-checksum')
    explicit = N(27, S('Box'), L([N(2, S('a'), N(10))]),
                 L([N(25, S('Box'), L([N(20, S('a'))]))]))
    units, fragments = [], []
    for group, own, value, params, uses in [
            ('g-main', X(1, 'main'), N(77, I(7)), [], []),
            ('g-unused', X(2, 'unused'), N(70, X(3, 'main')), [X(3, 'main')], [X(3, 'main')])]:
        body = N(75, own, value, UNIT)
        closed = body
        for parameter in reversed(params):
            closed = N(71, parameter, TY, closed)
        header = N(240, S(group), L([]), L([]), L([explicit]), L([]), L([]),
                   L([N(2, C.fields(own, 31, 2)[1], TY)]), S('native-vetted-fragment-checksum'))
        units.append(N(241, header, N(84, L([explicit]), closed)))
        fragments.append(N(401, S(group), S('native-audited-receipt'), L([S('Box')]),
                           L(params), body, L([own]), L(uses)))
    simple = C.items(C.fields(ci, 242, 13)[8])[0]
    package = N(430, S('MLF-OPEN-CRATE-1/checker-1'), S(C.compatibility_identity()),
        S(C.pack([C.interface_association(ci)])),
        L([N(2, S(key), S(C.fingerprint(TY))) for key in ['main', 'unused']]),
        L([N(2, S('Box'), S(C.fingerprint(C.declaration_hash_value(simple))))]), L(fragments))
    old = {'.mlfci': C.tree_document([ci], 3),
           '.mlfco': C.tree_document([N(243, N(6), ci, L(units))], 4)}
    opened = refresh(package)
    return {'closed_files': old, 'open_files': opened, 'dependency_interfaces': [],
            'audited_open_files': dict(opened),
            'closed_linked_bytes': C.tree_document([linked()], 6),
            'open_linked_bytes': C.tree_document([linked(111, 112)], 6)}

def refresh(package, interface=None):
    raw = C.tree_document([package], 7)
    interface = iface('') if interface is None else interface
    fields = list(C.fields(interface, 242, 13))
    fields[11] = S(hashlib.sha256(raw).hexdigest())
    return {'.mlfco': raw, '.mlfci': C.tree_document([N(242, *fields)], 3)}

def mutate(data, callback, audit=True):
    result = copy.deepcopy(data)
    root = list(C.fields(C.decoded(result['open_files']['.mlfco'], 7), 430, 6))
    callback(root)
    result['open_files'] = refresh(N(430, *root))
    if audit:
        result['audited_open_files'] = dict(result['open_files'])
    return result

class ComparatorControls(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
    def rejects(self, data, message=None):
        with self.assertRaises(C.ComparisonError) as error:
            C.compare_open_file(**data)
        if message:
            self.assertIn(message, str(error.exception))
    def test_positive_complete_private_body_and_linked_alpha(self):
        result = C.compare_open_file(**self.data)
        self.assertEqual(result['fragment_count'], 2)
        self.assertTrue(result['all_original_fragment_bodies_exact'])
        self.assertEqual(result['linked']['changed_identity_pairs'], [(101,111),(102,112)])
        self.assertEqual([g['all_star_representation_pairs'] for g in result['groups']], [1,1])
    def test_positive_external_scheme_alpha_and_negative_capture(self):
        v = lambda x: N(30, I(x))
        a = N(46, v(4), N(41), N(43, N(40,v(4)), N(40,v(4))))
        b = N(46, v(0), N(41), N(43, N(40,v(0)), N(40,v(0))))
        self.assertTrue(C.type_alpha(a,b))
        bad = N(46, v(0), N(41), N(43, N(40,v(4)), N(40,v(0))))
        self.assertFalse(C.type_alpha(a,bad))
        # Forall's bound is outside the new binder scope.
        a = N(46,v(4),N(40,v(8)),N(40,v(4)))
        b = N(46,v(0),N(40,v(8)),N(40,v(0)))
        self.assertTrue(C.type_alpha(a,b))
        self.assertFalse(C.type_alpha(a,N(46,v(0),N(40,v(0)),N(40,v(0)))))
    def test_wrong_binary_family(self):
        data = copy.deepcopy(self.data)
        root = C.decoded(data['open_files']['.mlfco'],7)
        data['open_files']['.mlfco'] = C.tree_document([root],4)
        data['audited_open_files'] = dict(data['open_files'])
        self.rejects(data)
    def test_wrong_declared_family(self):
        self.rejects(mutate(self.data,lambda root:root.__setitem__(0,S('wrong-family'))),'family')
    def test_wrong_compiler_identity(self):
        self.rejects(mutate(self.data,lambda root:root.__setitem__(1,S('0'*64))),'compatibility')
    def test_private_same_type_body_changed_even_with_matching_audit(self):
        def change(root):
            entries = list(C.items(root[5]))
            fragment = list(C.fields(entries[1],401,7))
            body = list(C.fields(fragment[4],75,3))
            body[1] = N(77,I(8))
            fragment[4] = N(75,*body)
            fragment[6] = L([])
            entries[1] = N(401,*fragment)
            root[5] = L(entries)
        self.rejects(mutate(self.data,change),'body changed')
    def test_interface_content_changed(self):
        data = copy.deepcopy(self.data)
        root = C.decoded(data['open_files']['.mlfco'],7)
        fields = list(C.fields(C.decoded(data['open_files']['.mlfci'],3),242,13))
        fields[2] = L([S('Other')])
        data['open_files'] = refresh(root,N(242,*fields))
        data['audited_open_files'] = dict(data['open_files'])
        self.rejects(data,'interface content')
    def test_ownership_changed(self):
        def change(root):
            entries=list(C.items(root[5])); fs=list(C.fields(entries[1],401,7))
            fs[5]=L([X(9,'main')]);entries[1]=N(401,*fs);root[5]=L(entries)
        self.rejects(mutate(self.data,change),'owned binder')
    def test_duplicate_group(self):
        def change(root):
            es=list(C.items(root[5]));root[5]=L([es[0],es[0]])
        self.rejects(mutate(self.data,change))
    def test_reordered_groups(self):
        self.rejects(mutate(self.data,lambda root:root.__setitem__(5,L(reversed(C.items(root[5]))))),
                     'ordered fragment')
    def test_binding_reference_hash(self):
        def change(root):
            refs=list(C.items(root[3]));k,_=C.fields(refs[0],2,2);refs[0]=N(2,k,S('0'*64));root[3]=L(refs)
        self.rejects(mutate(self.data,change),'reference hash')
    def test_datatype_reference_hash(self):
        def change(root):
            refs=list(C.items(root[4]));k,_=C.fields(refs[0],2,2);refs[0]=N(2,k,S('0'*64));root[4]=L(refs)
        self.rejects(mutate(self.data,change),'reference hash')
    def test_reference_order_and_duplicate(self):
        for transform in [lambda xs:list(reversed(xs)),lambda xs:[xs[0],xs[0]]]:
            self.rejects(mutate(self.data,lambda root:root.__setitem__(3,L(transform(C.items(root[3]))))),
                         'reference order/duplicate')
    def test_interface_association(self):
        self.rejects(mutate(self.data,lambda root:root.__setitem__(2,S('changed'))),'association')
    def test_receipt_with_recomputed_outer_sha_requires_real_audit(self):
        negative=C.make_native_negatives(self.data['closed_files'],self.data['open_files'])[0]
        data=copy.deepcopy(self.data);data['open_files']=negative['open_files']
        self.rejects(data,'audited rebuild')
        self.assertEqual(negative['expected_helper_exit'],1)
    def test_used_inventory_with_recomputed_sha_and_matching_audit(self):
        negative=C.make_native_negatives(self.data['closed_files'],self.data['open_files'])[1]
        data=copy.deepcopy(self.data);data['open_files']=negative['open_files']
        data['audited_open_files']=dict(data['open_files'])
        self.rejects(data,'used-name inventory')
        self.assertEqual(negative['expected_helper_exit'],0)
    def test_native_mutator_contract_and_old_checksum_outer_consistency(self):
        negatives=C.make_native_negatives(self.data['closed_files'],self.data['open_files'])
        self.assertEqual(len(negatives),3)
        for case in negatives[:2]:
            files=case['open_files'];fields=C.fields(C.decoded(files['.mlfci'],3),242,13)
            self.assertEqual(C.text(fields[11]),hashlib.sha256(files['.mlfco']).hexdigest())
        old=negatives[2]['closed_files'];ci=C.decoded(old['.mlfci'],3)
        self.assertEqual(C.fields(C.decoded(old['.mlfco'],4),243,3)[1],ci)
        self.assertNotEqual(old,self.data['closed_files'])
        self.assertEqual(negatives[2]['expected_helper_exit'],1)
    def test_nonstar_declaration_is_not_erased(self):
        simple=C.items(C.fields(iface('x'),242,13)[8])[0]
        fs=list(C.fields(simple,26,3));fs[1]=L([N(2,S('a'),N(11,N(10),N(10)))])
        with self.assertRaises(C.ComparisonError):
            C.same_declaration(simple,N(27,*fs))
    def test_linked_capture_or_wrong_use(self):
        data=copy.deepcopy(self.data)
        wrong=N(84,L([]),N(75,X(111,'main'),N(77,I(7)),
                    N(75,X(112,'unused'),N(70,X(112,'main')),N(70,X(111,'main')))))
        data['open_linked_bytes']=C.tree_document([wrong],6)
        self.rejects(data)
    def test_linked_free_renaming_rejected(self):
        with self.assertRaises(C.ComparisonError):
            C.linked_equal(N(70,X(1,'free')),N(70,X(2,'free')))
    def test_linked_noninjective_rejected(self):
        data=copy.deepcopy(self.data);data['open_linked_bytes']=C.tree_document([linked(111,111)],6)
        self.rejects(data,'injective')
    def test_linked_type_or_computation_change_rejected(self):
        with self.assertRaises(C.ComparisonError):
            C.linked_equal(N(74,N(77,I(1)),N(58,N(50),N(55))),
                           N(74,N(77,I(1)),N(58,N(55),N(50))))
    def test_linked_ieee_bits_exact(self):
        with self.assertRaises(C.ComparisonError):
            C.linked_equal(N(78,('bits',0)),N(78,('bits',1<<63)))
    def test_input_trailing_byte_rejected(self):
        data=copy.deepcopy(self.data);data['open_files']['.mlfco']+=b'x'
        self.rejects(data)
    def test_audit_interface_not_just_object_compared(self):
        data=copy.deepcopy(self.data);data['audited_open_files']['.mlfci']+=b'x'
        self.rejects(data,'audited rebuild')
    def test_extra_artifact_file_rejected(self):
        data=copy.deepcopy(self.data);data['open_files']['extra']=b''
        self.rejects(data,'file inventory')

if __name__=='__main__':
    unittest.main()
