"""Stage04 host-only tests. Running this file NEVER compiles or launches native.

Execution is forbidden until the parent freezes this exact source and command.
The approved initial process writes test evidence then exactly twelve fixture
source sets and STOPS for independent generated-source review.
"""
from __future__ import annotations
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from resource_ir_v8.packet import emit_packet,loads_packet,_fresh_specification,_verify_packet
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8 import metadata
from resource_ir_v8 import packet_budget as pb
from stage04_packet_oracle import canon,exact,verify_emission,verify_specification,independent_expected,verify_source_text,SCHEMA,NULL
from stage04_packet_fixture_driver import generate_all

HERE=Path(__file__).parent
DATA=json.loads((HERE/'stage04_packet_cases.json').read_text())
FIXTURE=HERE/'fixtures'/'ir8-metadata.json'
FIXTURE_BYTES=FIXTURE.read_bytes()
assert hashlib.sha256(FIXTURE_BYTES).hexdigest()==DATA['stage03_fixture_sha256']
CASES=json.loads(FIXTURE_BYTES)['cases'];BY_NAME={c['name']:c for c in CASES}
RECORDS=[]
EVIDENCE=None
HOST_ARTIFACT_BYTES=0
NATIVE_NAMES={c['name'] for c in DATA['native_fixtures']}

def retain_host_only(name,result):
    global HOST_ARTIFACT_BYTES
    if name in NATIVE_NAMES:return []
    assert EVIDENCE is not None
    directory=EVIDENCE/'host-only'/name;directory.mkdir(parents=True,exist_ok=False)
    files=[]
    receipt=canon(dict(format='ir8-stage04-host-artifact/1',fixture=name,manifest_json=result.manifest_json,manifest_sha256=result.manifest_sha256,supplement_json=result.supplement_json,supplement_sha256=result.supplement_sha256))
    for filename,content in [('ir8_packet_generated.h',result.packet_header),('ir8_packet_generated.c',result.packet_source),('host-receipt.json',receipt)]:
        payload=content.encode('utf-8')
        if HOST_ARTIFACT_BYTES+len(payload)>134217728:raise ValueError('host-only retained artifacts exceed 128MiB')
        with (directory/filename).open('xb') as stream:stream.write(payload)
        HOST_ARTIFACT_BYTES+=len(payload);files.append(dict(path='host-only/'+name+'/'+filename,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest()))
    return files


def raw(name='concrete_empty_finish'):return json.loads(BY_NAME[name]['text'])


def diagnosis(call):
    try:call()
    except Exception as exc:
        if not all(hasattr(exc,k) for k in ('path','layer','code','message')):raise
        return dict(path=exc.path,layer=exc.layer,code=exc.code,message=exc.message)
    raise AssertionError('operation unexpectedly accepted')


class RawCases(unittest.TestCase):
    def run_case(self,case):
        text=case['text'];payload=text.encode('utf-8')
        self.assertEqual(len(payload),case['input_bytes']);self.assertEqual(hashlib.sha256(payload).hexdigest(),case['input_sha256'])
        if not case['accepted']:
            result=diagnosis(lambda:loads_packet(text))
            exact({k:result[k] for k in ('layer','code','path')},{k:case['expected_'+k] for k in ('layer','code','path')},case['name'])
            RECORDS.append(dict(name=case['name'],status='expected-lower-rejection',diagnostic=result));return
        result=loads_packet(text);x=verify_emission(json.loads(text),result)
        # Separate observed private output is compared against independent equations.
        # It is not used to construct expected values or qualify emitted C alone.
        verify_specification(json.loads(text),_fresh_specification(json.loads(text)))
        self.assertEqual(result.format,'resource-ir-v8-c-packet-source/1')
        self.assertLessEqual(sum(len(getattr(result,k).encode()) for k in ('packet_header','packet_source')),33554432)
        self.assertLessEqual(len(result.manifest_json.encode()),8388608)
        self.assertLessEqual(len(result.supplement_json.encode()),1048576)
        for k,limit in [('creation_units',2097152),('work_units',16777216)]:self.assertLessEqual(dict(result.statistics)[k],limit)
        RECORDS.append(dict(name=case['name'],status='host-emission-only',declared_outcome='accepted',artifacts=retain_host_only(case['name'],result),raw_sha256=case['input_sha256'],metadata_sha256=x['closure'].metadata_sha256,supplement_sha256=result.supplement_sha256,manifest_sha256=result.manifest_sha256,source_sha256=hashlib.sha256(result.packet_source.encode()).hexdigest()))


def raw_case(case):
    def test(self):self.run_case(case)
    return test
for case in CASES:setattr(RawCases,'test_raw_'+case['name'],raw_case(case))


class HostBoundary(unittest.TestCase):
    def test_public_raw_entrypoint_and_order(self):
        p=raw('concrete_nullary_case_all_arms')
        def reverse(v):
            if type(v) is dict:return {k:reverse(v[k]) for k in reversed(tuple(v))}
            if type(v) is list:return [reverse(x) for x in v]
            return v
        a=emit_packet(p);b=emit_packet(reverse(p));c=loads_packet(canon(p))
        for field in dataclasses.fields(a):
            if field.name!='statistics':exact(getattr(a,field.name),getattr(b,field.name));exact(getattr(a,field.name),getattr(c,field.name))
        verify_emission(p,a)
    def test_immutable_result_and_nested_fields(self):
        result=emit_packet(raw())
        self.assertFalse(hasattr(result,'__dict__'))
        for field in dataclasses.fields(result):
            value=getattr(result,field.name)
            self.assertIn(type(value),(str,bytes,tuple))
            with self.assertRaises((AttributeError,dataclasses.FrozenInstanceError)):setattr(result,field.name,value)
        pending=[result.statistics,result.bindings]
        while pending:
            value=pending.pop();self.assertIn(type(value),(str,bytes,int,tuple))
            if type(value) is tuple:pending.extend(value)
    def test_every_public_call_checks_resources_freshly(self):
        original=metadata._check_resources
        with patch.object(metadata,'_check_resources',wraps=original) as spy:
            p=raw();emit_packet(p);loads_packet(canon(p));p['version']=7
            diagnosis(lambda:emit_packet(p))
            self.assertEqual(spy.call_count,3)
    def test_previous_result_is_not_ingress(self):
        result=emit_packet(raw());error=diagnosis(lambda:emit_packet(result))
        self.assertEqual((error['layer'],error['code']),('schema','SCHEMA'))
    def test_metadata_closure_is_not_ingress(self):
        c=check_metadata(raw());error=diagnosis(lambda:emit_packet(c))
        self.assertEqual((error['layer'],error['code']),('schema','SCHEMA'))
    def test_derived_tables_are_not_ingress(self):
        d=json.loads(check_metadata(raw()).metadata_json)
        error=diagnosis(lambda:emit_packet(d))
        self.assertEqual(error['layer'],'schema')
    def test_json_input_does_not_accept_dictionary(self):
        error=diagnosis(lambda:loads_packet(raw()))
        self.assertEqual(error['layer'],'schema')
    def test_private_verifier_rechecks_and_returns_no_authority(self):
        p=raw();candidate=_fresh_specification(p);original=metadata._check_resources
        with patch.object(metadata,'_check_resources',wraps=original) as spy:
            self.assertIsNone(_verify_packet(p,candidate));self.assertEqual(spy.call_count,1)
            p['version']=7;error=diagnosis(lambda:_verify_packet(p,candidate));self.assertEqual(spy.call_count,2)
            self.assertEqual((error['layer'],error['code']),('schema','VERSION'))
    def test_private_bool_does_not_equal_zero(self):
        p=raw();candidate=_fresh_specification(p)
        obj=next(o for o in candidate['objects'] if o['key']=='table/environments')
        obj['rows'][0]['id']=False
        error=diagnosis(lambda:_verify_packet(p,candidate))
        self.assertEqual((error['layer'],error['code'],error['path']),('packet-mapping','EQUATION','packet.specification'))
        RECORDS.append(dict(name='private-bool-integer',classification='private-mutation-not-public-capacity',diagnostic=error))
    def test_private_negative_and_overwide_integer(self):
        for value in (-1,4294967296):
            p=raw();candidate=_fresh_specification(p)
            obj=next(o for o in candidate['objects'] if o['key']=='table/environments');obj['rows'][0]['id']=value
            error=diagnosis(lambda:_verify_packet(p,candidate));self.assertEqual((error['layer'],error['code'],error['path']),('packet-mapping','EQUATION','packet.specification'))
    def test_private_omission_and_extra_object(self):
        for action in ('omit','extra'):
            p=raw();candidate=_fresh_specification(p)
            if action=='omit':candidate['objects'].pop()
            else:candidate['objects'].append(copy.deepcopy(candidate['objects'][0]))
            error=diagnosis(lambda:_verify_packet(p,candidate));self.assertEqual(error['layer'],'packet-mapping')
    def test_nullary_sum_supplement_not_derived_from_slots(self):
        p=raw('concrete_nullary_case_all_arms');x=independent_expected(p)
        sums=[r for r in x['supplement']['sites'] if r['sum_family'] is not None]
        self.assertEqual(len(sums),1);self.assertEqual(sums[0]['sum_variant'],0)
        self.assertFalse([s for s in x['metadata']['slots'] if s['site']==sums[0]['site']])
        candidate=_fresh_specification(p);candidate['supplement']['sites'][sums[0]['site']]['sum_variant']=1
        error=diagnosis(lambda:_verify_packet(p,candidate));self.assertEqual(error['layer'],'packet-mapping')
    def test_hostile_legal_names_remain_numeric_bytes(self):
        p=raw('concrete_nullary_case_all_arms');old='Choice';new='Q"\\\n/*x*/#include <evil> λ😀'
        p['families'][new]=p['families'].pop(old)
        for op in p['entry']:
            if op.get('family')==old:op['family']=new
        result=emit_packet(p);x=verify_emission(p,result)
        self.assertNotIn(new,result.packet_source);self.assertNotIn('evil',result.packet_source)
        self.assertNotIn('λ',result.packet_source);self.assertNotIn('😀',result.packet_source)
        self.assertEqual([line for line in result.packet_source.splitlines() if line.startswith('#include')],['#include "ir8_packet_generated.h"'])
        self.assertTrue(any(b>=128 for b in x['values']['pool/strings']))
    def test_nul_name_rejected(self):
        p=raw();p['families']['bad\x00name']={'variants':['A'],'fields':{'A':[]}}
        error=diagnosis(lambda:emit_packet(p))
        self.assertEqual((error['layer'],error['code'],error['path']),('declarations','NAME','families'))
    def test_raw_boolean_and_nonversion_integers(self):
        for value in (True,False,-1,4294967296):
            p=raw();p['version']=value;error=diagnosis(lambda:emit_packet(p))
            self.assertEqual((error['layer'],error['code'],error['path']),('schema','VERSION','program.version'))
    def test_surrogate_json_rejected_before_parse(self):
        error=diagnosis(lambda:loads_packet('"\ud800"'))
        self.assertEqual((error['layer'],error['code'],error['path']),('schema','UTF8','program'))
    def test_binary_json_ingress_rejected(self):
        error=diagnosis(lambda:loads_packet(b'\xff'))
        self.assertEqual((error['layer'],error['code'],error['path']),('schema','JSON','program'))
    def test_independent_source_parser_rejects_extra_storage(self):
        p=raw();result=emit_packet(p);x=independent_expected(p)
        for extra in ('static const unsigned char extra[1]={0};\n','void invented_body(void) {}\n'):
            with self.assertRaises(AssertionError):verify_source_text(x,result.packet_header,result.packet_source+extra)
    def test_independent_source_parser_rejects_changed_numeric_field(self):
        p=raw();result=emit_packet(p);x=independent_expected(p)
        original='.id=UINT32_C(0)';self.assertIn(original,result.packet_source)
        changed=result.packet_source.replace(original,'.id=UINT32_C(1)',1)
        with self.assertRaises(AssertionError):verify_source_text(x,result.packet_header,changed)
    def test_packet_exports_no_execution_authority(self):
        import resource_ir_v8.packet as packet
        self.assertEqual(set(packet.__all__),{'PacketEmission','PacketError','emit_packet','loads_packet'})
        for name in ('execute','run','evaluate','open_runtime','compile','check_source'):self.assertFalse(hasattr(packet,name))
    def test_oracle_type_exact_comparison(self):
        with self.assertRaises(AssertionError):exact({'x':False},{'x':0})
        with self.assertRaises(AssertionError):exact({'x':None},{'x':NULL})


class PrivateBudgetControls(unittest.TestCase):
    """Private arithmetic/write controls only, no public capacity claims."""
    def test_plain_integer_domain(self):
        self.assertEqual(pb.uint(0,'test.integer'),0);self.assertEqual(pb.uint(NULL,'test.integer'),NULL)
        for value in (False,True,-1,NULL+1):
            error=diagnosis(lambda:pb.uint(value,'test.integer'))
            self.assertEqual((error['layer'],error['code'],error['path']),('packet-schema','INTEGER','test.integer'))
    def test_nullable_domain(self):
        self.assertEqual(pb.uint(None,'test.null',nullable=True),NULL)
        error=diagnosis(lambda:pb.uint(NULL,'test.null',nullable=True))
        self.assertEqual((error['layer'],error['code'],error['path']),('packet-schema','NULL_DOMAIN','test.null'))
    def test_creation_limit_atomic(self):
        b=pb.Budget();b.reserve(creation=2097152)
        error=diagnosis(lambda:b.reserve(creation=1,work=1))
        self.assertEqual((b.creation_units,b.work_units),(2097152,0))
        self.assertEqual((error['layer'],error['code'],error['path']),('packet-bounds','CREATION_UNITS','packet.creation_units'))
    def test_work_limit_atomic(self):
        b=pb.Budget();b.reserve(work=16777216)
        error=diagnosis(lambda:b.reserve(creation=1,work=1))
        self.assertEqual((b.creation_units,b.work_units),(0,16777216))
        self.assertEqual((error['layer'],error['code'],error['path']),('packet-bounds','WORK_UNITS','packet.work_units'))
    def test_source_byte_budget_shared_between_writers(self):
        b=pb.Budget();a=pb.Writer(b,'source',4);a.emit(b'abc');c=pb.Writer(b,'source',4);c.emit(b'd')
        error=diagnosis(lambda:c.emit(b'e'));self.assertEqual(b.source_utf8_bytes,4)
        self.assertEqual((error['layer'],error['code'],error['path']),('packet-bounds','SOURCE_BYTES','packet.source_bytes'))
    def test_manifest_byte_reservation(self):
        b=pb.Budget();w=pb.Writer(b,'manifest',4);w.emit(b'1234')
        error=diagnosis(lambda:w.emit(b'5'));self.assertEqual(b.manifest_utf8_bytes,4)
        self.assertEqual((error['layer'],error['code'],error['path']),('packet-bounds','MANIFEST_BYTES','packet.manifest_bytes'))
    def test_supplement_byte_reservation(self):
        b=pb.Budget();w=pb.Writer(b,'supplement',4);w.emit(b'1234')
        error=diagnosis(lambda:w.emit(b'5'));self.assertEqual(b.supplement_utf8_bytes,4)
        self.assertEqual((error['layer'],error['code'],error['path']),('packet-bounds','SUPPLEMENT_BYTES','packet.supplement_bytes'))
    def test_source_chunk_limit(self):
        b=pb.Budget();w=pb.Writer(b,'source',33554432);w.emit(b'x'*4096)
        error=diagnosis(lambda:w.emit(b'x'*4097));self.assertEqual(b.source_utf8_bytes,4096)
        self.assertEqual((error['layer'],error['code'],error['path']),('packet-source','SOURCE_GRAMMAR','packet.source'))
    def test_error_properties_immutable(self):
        e=pb.PacketError('test','packet-schema','INTEGER','diagnostic')
        for name in ('path','layer','code','message'):
            with self.assertRaises(AttributeError):setattr(e,name,'changed')


if __name__=='__main__':
    evidence=Path(os.environ['STAGE04_TEST_EVIDENCE'])
    if evidence.exists() or evidence.is_symlink():raise ValueError('fresh evidence path required')
    evidence.mkdir()
    EVIDENCE=evidence
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    with (evidence/'HOST_RESULTS.json').open('x') as stream:stream.write(canon(dict(format='ir8-stage04-host-results/1',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),records=RECORDS,native_executed=False,graph_executed=False,source_admitted=False)))
    if not result.wasSuccessful() or result.skipped:raise SystemExit(1)
    generation=generate_all(evidence/'native')
    print(canon(dict(status='host-only-stop-before-compile',tests=result.testsRun,generated_fixtures=len(generation['fixtures']),native_executed=False,graph_executed=False,source_admitted=False)))
