#!/usr/bin/env python3
"""Finite, predeclared cross-language corpus; expected outcomes are specification-derived."""
from dataclasses import dataclass, replace
import struct
from artifact_binary_reference import Limits, Writer, explicit_document, repair_crc, tree_document, MIN_I, MAX_I

@dataclass(frozen=True)
class Case:
    name: str
    data: bytes
    accepts: bool
    schema: int = 7
    limits: Limits = Limits()
    roots: tuple = ()

SCALAR_ROOTS = tuple([('int', x) for x in (MIN_I, -65536, -129, -128, -1, 0, 1, 63, 64, 127, 128, 65535, MAX_I)] +
    [('bits', x) for x in (0, MIN_I, 1, 0x000fffffffffffff, 0x0010000000000000,
        0x3ff0000000000000, 0x7fefffffffffffff, 0x7ff0000000000000, -0x10000000000000,
        0x7ff8000000000001, 0x7ff0000000000001, -2251799813685247)] +
    [('text', x) for x in ('', '\0', 'ASCII', 'α😀', '\x7f\x80\u07ff\u0800\ud7ff\ue000\uffff\U00010000\U0010ffff', 'a\0b')])
SHARED_LEAF = ('node', 31, (('int', -7), ('text', 'same hint\0😀')))
SHARED_ROOTS = (('node', 70, (SHARED_LEAF,)), ('node', 72, (SHARED_LEAF, SHARED_LEAF)),
                ('node', 72, (SHARED_LEAF, SHARED_LEAF)), ('text', 'same hint\0😀'))

def word(raw, offset, value, crc=True):
    out = bytearray(raw); struct.pack_into('<I', out, offset, value)
    return repair_crc(out) if crc else bytes(out)

def sections(raw, *, symbols=None, nodes=None, roots=None):
    header = list(struct.unpack_from('<18I', raw, 8))
    old_s, old_n, old_r = header[6], header[9], header[13]
    s = raw[old_s:old_n] if symbols is None else symbols
    n = raw[old_n:old_r] if nodes is None else nodes
    r = raw[old_r:] if roots is None else roots
    header[4] = 80 + len(s+n+r); header[7] = len(s); header[9] = 80 + len(s)
    header[10] = len(n); header[13] = 80 + len(s+n); header[14] = len(r); header[17] = 0
    return repair_crc(raw[:8] + struct.pack('<18I', *header) + s+n+r)

def corpus():
    cases = []
    def good(name, roots, **kw):
        cases.append(Case(name, tree_document(roots), True, roots=tuple(roots), **kw))
    def bad(name, data, **kw): cases.append(Case(name, data, False, **kw))
    # Exercise the fused and checksum-first symbol paths with independently
    # authored bytes at both thresholds. All values remain within wire limits.
    multibyte = 'a' * 1025 + 'é中😀' + 'b' * 32
    good('scan-mixed-widths', (('text',''),('text',multibyte),('text','end')))
    good('scan-symbol-cap', (('text','a' * 65533),))       # 3-byte length = 65536
    good('scan-symbol-over-cap', (('text','a' * 65534),))
    for count in (1024,1025):
        good('scan-count-'+str(count), tuple(('text',str(i)) for i in range(count)))
    valid = tree_document((('text',multibyte),))
    location = valid.index('😀'.encode())
    for name, replacement in [('continuation',0x41),('overlong',0x80)]:
        mutated = bytearray(valid)
        mutated[location+1] = replacement
        bad('scan-invalid-'+name,repair_crc(mutated))
    for name,offset in [('symbol',location),('node',struct.unpack_from('<I',valid,44)[0]),('root',-1)]:
        mutated = bytearray(valid); mutated[offset] ^= 1
        bad('scan-crc-'+name,bytes(mutated))
    good('empty', ())
    good('int-zero', (('int', 0),))
    good('all-scalars', SCALAR_ROOTS)
    good('structural-sharing', SHARED_ROOTS)
    good('ordered-distinct-roots', (('int', 2), ('int', 1), ('int', 2)))
    good('same-id-different-hint', (('node', 31, (('int', 9), ('text', 'a'))),
                                    ('node', 31, (('int', 9), ('text', 'b')))))
    good('same-hint-different-id', (('node', 31, (('int', 9), ('text', 'a'))),
                                    ('node', 31, (('int', 10), ('text', 'a')))))
    # These have identical byte lengths to the decoder's optional text hint.
    # Cross the table-CRC threshold and cover mismatches at either end.
    run = 'A' * 1100
    for label, value in [('equal', run), ('first', 'B' + run[1:]),
                         ('last', run[:-1] + 'B'), ('unicode', run[:-2] + 'é')]:
        good('long-symbol-' + label, (('text', value),))
    valid = tree_document((('text', run),))
    for index, label in [(valid.index(run.encode()), 'first'), (valid.index(run.encode()) + len(run) - 1, 'last')]:
        raw = bytearray(valid)
        raw[index] = 255
        bad('long-symbol-invalid-' + label, repair_crc(raw))
    good('max-node-tag', (('node', 2147483647, ()),))
    base = tree_document((('int', 0),))
    empty = tree_document(())
    for n in (0, 1, 7, 8, 20, 76, 79, 80, len(base)-1): bad('truncated-' + str(n), base[:n])
    bad('magic-first-byte', b'X' + base[1:])
    for offset, value, label in [(8,0,'version-zero'), (8,2,'version-future'), (12,1,'flags'),
        (16,8,'schema'), (20,79,'header-length'), (24,len(base)-1,'total-short'),
        (24,len(base)+1,'total-long'), (28,1,'symbol-count'), (32,81,'symbol-offset'),
        (36,1,'symbol-length'), (40,0,'node-count'), (44,81,'node-offset'),
        (48,1,'node-length'), (52,1,'edge-count'), (56,0,'root-count'),
        (60,80,'root-offset'), (64,0,'root-length'), (68,2,'node-width'), (72,2,'symbol-width')]:
        bad('header-' + label, word(base, offset, value))
    for offset,label in [(28,'symbols'),(40,'nodes'),(52,'edges'),(56,'roots')]:
        bad('header-huge-'+label,word(base,offset,0xffffffff))
    for offset,label in [(68,'node'),(72,'symbol')]:
        for value in (0,33,0xffffffff):bad('header-width-'+label+'-'+str(value),word(base,offset,value))
    bad('crc-mismatch', word(base, 76, 0, crc=False))
    bad('payload-crc-mismatch', base[:-1] + bytes([base[-1] ^ 1]))
    bad('trailing-byte', base + b'\0')
    bad('empty-plus-node', explicit_document([], [(0,0)], []))
    bad('empty-plus-symbol', explicit_document(['unused'], [], []))
    bad('root-out-of-range', explicit_document([], [(0,0)], [1]))
    bad('child-self-cycle', explicit_document([], [(3,(0,(0,)))], [0]))
    bad('child-forward', explicit_document([], [(3,(0,(1,))), (0,0)], [0]))
    bad('duplicate-int-node', explicit_document([], [(0,0),(0,0)], [0,1]))
    bad('duplicate-bits-node', explicit_document([], [(1,1),(1,1)], [0,1]))
    bad('duplicate-text-node', explicit_document(['x'], [(2,0),(2,0)], [0,1]))
    bad('duplicate-structural-node', explicit_document([], [(0,0),(3,(9,(0,))),(3,(9,(0,)))], [1,2]))
    bad('duplicate-symbol', explicit_document(['x','x'], [(2,0),(2,1)], [0,1]))
    bad('unused-symbol', explicit_document(['x','y'], [(2,0)], [0]))
    bad('out-of-order-first-symbol', explicit_document(['x','y'], [(2,1),(2,0)], [0,1]))
    bad('text-symbol-out-of-range', explicit_document(['x'], [(2,1)], [0]))
    bad('unused-node', explicit_document([], [(0,0),(0,1)], [1]))
    bad('root-postorder', explicit_document([], [(0,0),(0,1)], [1,0]))
    bad('children-postorder', explicit_document([], [(0,0),(0,1),(3,(5,(1,0)))], [2]))
    bad('node-padding-byte', sections(base, nodes=base[80:82]+b'\0'))
    bad('root-padding-byte', sections(base, roots=base[-1:]+b'\0'))
    bad('node-padding-bits', sections(base, nodes=bytes([base[80], base[81] | 128])))
    bad('root-padding-bits', sections(base, roots=bytes([128])))
    bad('node-tag-too-large', explicit_document([], [(3,(2147483648,()))], [0]))
    for encoded, label in [(b'\x80\0','overlong-zero'), (b'\x81\0','overlong-one'),
        (b'\x80'*9+b'\2','overflow'), (b'\xff'*10,'continued-tenth'),
        (b'\x80'*10+b'\0','eleven-groups'), (b'\x80','truncated')]:
        bits = Writer(); bits.put(0,2)
        for b in encoded: bits.put(b,8)
        bad('int-varint-' + label, sections(base,nodes=bits.bytes()))
    for tag_bytes, count_bytes, label in [(b'\x80\0',b'\0','tag-overlong'),
        (b'\0',b'\x80\0','arity-overlong'),(b'\0',b'\xff'*9+b'\2','arity-overflow')]:
        bits=Writer();bits.put(3,2)
        for b in tag_bytes+count_bytes:bits.put(b,8)
        bad('node-varint-'+label,sections(base,nodes=bits.bytes()))
    text_base = tree_document((('text','x'),))
    bad('symbol-varint-overlong', sections(text_base,symbols=b'\x81\0x'))
    bad('symbol-section-trailing', sections(text_base,symbols=b'\1x\0'))
    bad('symbol-length-truncated', sections(text_base,symbols=b'\2x'))
    for data, label in [(b'\x80','continuation'),(b'\xc0\x80','overlong-nul'),
        (b'\xe0\x80\x80','overlong-three'),(b'\xf0\x80\x80\x80','overlong-four'),
        (b'\xed\xa0\x80','surrogate-first'),(b'\xed\xbf\xbf','surrogate-last'),
        (b'\xf4\x90\x80\x80','above-unicode'),(b'\xf5\x80\x80\x80','bad-lead'),
        (b'\xff','ff'),(b'\xe2\x82','truncated'),(b'\xc2x','bad-follow')]:
        bad('utf8-' + label, explicit_document([data],[(2,0)],[0]))
    limits = Limits()
    for field, value, raw, label in [
        ('bytes',80,base,'bytes'), ('symbols',0,text_base,'symbols'),
        ('symbol_bytes',0,text_base,'single-symbol'), ('total_symbol_bytes',0,text_base,'total-symbol'),
        ('nodes',0,base,'nodes'), ('edges',0,base,'roots')]:
        changes = {field:value}
        if field=='total_symbol_bytes': changes['symbol_bytes']=0
        if field=='bytes': changes.update(symbol_bytes=0,total_symbol_bytes=0)
        bad('limit-' + label, raw, limits=replace(limits, **changes))
    chain = [(0,0)] + [(3,(2,(i-1,))) for i in range(1,9)]
    chain_bytes = explicit_document([], chain, [8])
    bad('limit-depth',chain_bytes,limits=replace(limits,depth=8))
    cases.append(Case('depth-exact-boundary',chain_bytes,True,limits=replace(limits,depth=9)))
    bomb = [(0,0)] + [(3,(2,(i-1,i-1))) for i in range(1,16)]
    bad('limit-dag-expansion',explicit_document([],bomb,[15]),limits=replace(limits,work=65534))
    cases.append(Case('dag-work-exact-boundary',explicit_document([],bomb,[15]),True,
                      limits=replace(limits,work=65535)))
    bad('limit-root-work',explicit_document([],[(0,0)],[0,0]),limits=replace(limits,work=1))
    bad('limit-text-work-utf8-bytes',tree_document((('text','😀'),)),limits=replace(limits,work=4))
    bad('limit-edges',explicit_document([],[(0,0),(3,(0,(0,0)))],[1]),limits=replace(limits,edges=1))
    for field, value in [('bytes',79),('depth',0),('depth',65537),('work',-1),('nodes',2147483648)]:
        bad('invalid-limits-'+field+'-'+str(value),empty,limits=replace(limits,**{field:value}))
    bad('invalid-limits-single-total',empty,limits=replace(limits,symbol_bytes=9,total_symbol_bytes=8))
    bad('invalid-limits-total-file',empty,limits=replace(limits,total_symbol_bytes=limits.bytes+1))
    return tuple(cases)
