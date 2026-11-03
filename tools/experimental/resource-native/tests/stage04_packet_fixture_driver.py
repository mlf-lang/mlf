"""Finite Stage04 SOURCE generator and separately invoked readback verifier.

Never starts a process. Generation ends before compilation. Verification reads
only previously captured native JSON, freshly checks raw and compares complete
semantic values plus compiler-measured member census via the independent oracle.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from stage04_packet_oracle import SCHEMA, ELEMENTS, NULL, TEST_CONFIG, bounded_file, canon, exact, independent_expected, verify_emission, verify_native, verify_report, verify_support

HERE=Path(__file__).parent
DATA=TEST_CONFIG
FIXTURE=HERE/'fixtures'/'ir8-metadata.json'
ROOT='struct Ir8Packet_generated_v1'


def ctext(text):
    assert all(ord(c)<128 for c in text)
    return json.dumps(text)


def say(text): return '(void)printf('+ctext(text)+');'


def member_print(expr,kind):
    if kind.startswith('V<'):return 'span('+expr+');'
    if kind.startswith('unsigned-char['):return 'bytes('+expr+',sizeof '+expr+');'
    if kind.startswith('Span['):
        n=int(kind[5:-1]);return "(void)putchar('[');"+''.join(("(void)putchar(',');" if i else '')+'span('+expr+'['+str(i)+']);' for i in range(n))+"(void)putchar(']');"
    return 'u32('+expr+');'


def struct_print(expr,fields):
    lines=[say('{')]
    for i,f in enumerate(fields):
        lines += [say((',' if i else '')+json.dumps(f['name'])+':'), member_print(expr+'.'+f['name'],f['type'])]
    lines.append(say('}'));return '\n'.join(lines)


def source_harness(x,mutations):
    report=next(t for t in SCHEMA['non_element_types'] if t['name']=='Report')
    report_lines=[say('{')]
    for i,f in enumerate(report['fields']):
        report_lines.append(say((',' if i else '')+json.dumps(f['name'])+':'))
        report_lines.append('(void)printf("%" PRIu64,r->work_used);' if f['name']=='work_used' else 'u32(r->'+f['name']+');')
    report_lines.append(say('}'))
    printers=[];abi=[say('[')]
    for idx,e in enumerate(SCHEMA['element_types']):
        ctype=e['c_type'];eid=e['element_type_id']
        body='u32(value);' if e['kind']=='scalar' else struct_print('value',e['fields'])
        printers.append('case '+str(eid)+': { '+ctype+' value;copy_at(&value,root,length,offset,sizeof value);'+body+'break; }')
        abi.append(say((',' if idx else '')+'{"element_type":'+str(eid)+',"bytes":'))
        abi.append('(void)printf("%zu",sizeof('+ctype+'));')
        abi.append(say(',"alignment":'))
        abi.append('(void)printf("%zu",_Alignof('+ctype+'));')
        abi.append(say(',"field_offsets":{'))
        if e['kind']!='scalar':
            for j,f in enumerate(e['fields']):
                abi.append(say((',' if j else '')+json.dumps(f['name'])+':'))
                abi.append('(void)printf("%zu",offsetof('+ctype+','+f['name']+'));')
        abi.append(say('},"field_bytes":{'))
        if e['kind']!='scalar':
            for j,f in enumerate(e['fields']):
                abi.append(say((',' if j else '')+json.dumps(f['name'])+':'))
                abi.append('(void)printf("%zu",sizeof((('+ctype+' *)0)->'+f['name']+'));')
        abi.append(say('}}'))
    abi.append(say(']'))
    census=[say('[')]
    for i,o in enumerate(x['objects']):
        ctype=ELEMENTS[o['element']]['c_type'];prefix=(',' if i else '')+'{"object":'+str(i)+',"count":'+str(o['count'])+',"offset":'
        census.append(say(prefix))
        census.append('(void)printf("%zu",offsetof('+ROOT+',o'+str(i)+'));' if o['count'] else 'u32(UINT32_MAX);')
        census.append(say(',"element_bytes":'))
        census.append('(void)printf("%zu",sizeof('+ctype+'));')
        census.append(say(',"element_alignment":'))
        census.append('(void)printf("%zu",_Alignof('+ctype+'));')
        census.append(say(',"object_bytes":'))
        census.append('(void)printf("%zu",sizeof((('+ROOT+' *)0)->o'+str(i)+'));' if o['count'] else 'u32(0);')
        census.append(say('}'))
    census.append(say(']'))
    binding='{ {'+','.join('{ {'+','.join(str(n) for n in bytes.fromhex(h))+'} }' for h in x['bindings'])+'} }'
    native_mutations=[]
    needs_store_helper=False
    for m in mutations:
        code=['(void)memcpy(copy,root,length);']
        for edit in m['edits']:
            object_id=next(i for i,o in enumerate(x['objects']) if o['key']==edit['key'])
            obj=x['objects'][object_id]
            assert edit['row']<obj['count'],(m['name'],edit)
            typ=ELEMENTS[obj['element']]['c_type']
            where='row_offset(copy,length,UINT32_C('+str(object_id)+'),UINT32_C('+str(edit['row'])+'))'
            if edit.get('field'):where+='+offsetof('+typ+','+edit['field']+')'
            if edit.get('component'):where+='+offsetof(Ir8PacketSpan,'+edit['component']+')'
            if 'byte' in edit:where+='+'+str(edit['byte'])
            ctype='unsigned char' if edit.get('byte_write') else 'uint32_t'
            needs_store_helper=True
            code.append('{ '+ctype+' value='+str(edit['value'])+';store_at(copy,length,'+where+ ',&value,sizeof value); }')
        code.append('mutation_result('+ctext(m['name'])+',copy,length,'+('1' if m.get('correspondence_reject') else '0')+');')
        # All bytewise comparisons are packet storage preservation, never padding
        # semantics or a substitute for decoded field correspondence.
        code.append('(void)memcpy(copy,root,length);')
        native_mutations.extend(code)
    tokens={'REPORT_COMPARE':' || '.join('report.'+f['name']+'!=repeated.'+f['name'] for f in report['fields']),'BINDINGS':binding,'REPORT_PRINTER':'\n'.join(report_lines),'ROW_PRINTERS':'\n'.join(printers),'ABI_PRINTER':'\n'.join(abi),'CENSUS_PRINTER':'\n'.join(census),'MUTATIONS':'\n'.join(native_mutations)}
    source=(HERE/'stage04_packet_native_harness.c').read_text()
    if not needs_store_helper:
        # This flag is set exactly where a store_at statement is emitted.
        # Empty mutation programs still retain the byte-aligned-copy control.
        unused_store='static void store_at(unsigned char *root, size_t length, size_t offset,\n                     const void *from, size_t bytes) {\n    if (offset > length || bytes > length - offset) die("mutation extent");\n    (void)memcpy(root + offset, from, bytes);\n}\n'
        assert source.count(unused_store)==1,'exact optional store helper'
        source=source.replace(unused_store,'',1)
    for key,value in tokens.items():source=source.replace('@STAGE04_'+key+'@',value)
    assert '@STAGE04_' not in source
    return source


def exclusive(directory,name,text,files):
    assert name in ('raw.json','ir8_packet_generated.h','ir8_packet_generated.c','stage04_harness.c','expected.json','mutations.json','generation.json','correspondence.json','manifest.json','supplement.json','control.json')
    path=directory/name
    if path.is_symlink():raise ValueError('symlink output')
    payload=text.encode('utf-8')
    if len(payload)>33554432:raise ValueError('per-file evidence ceiling')
    with path.open('xb') as stream:stream.write(payload)
    files.append(dict(name=name,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest()))


def make_mutations(name,x):
    """Resolve reviewed finite selectors against independent fresh metadata.

    No new raw baseline is constructed. Selectors must resolve exactly once;
    absence is a generation error, never a silently skipped control.
    """
    all_cases=[]
    for case in DATA['native_mutations']:
        if case['fixture']!=name:continue
        m=json.loads(canon(case))
        for edit in m['edits']:
            if type(edit['row']) is dict:
                select=edit['row'];rows=x['values'][edit['key']]
                hits=[i for i,r in enumerate(rows) if all(r[k]==v for k,v in select.items())]
                if 'pick_first' in edit:
                    assert hits,(name,case['name'],select);edit['row']=hits[0];edit.pop('pick_first')
                else:
                    assert len(hits)==1,(name,case['name'],select,hits);edit['row']=hits[0]
            if type(edit['value']) is dict:
                recipe=edit['value']
                if 'table_count' in recipe:edit['value']=len(x['metadata'][recipe['table_count']])
                elif 'object_count' in recipe:edit['value']=len(x['objects'])
                elif 'current_plus' in recipe:
                    row=x['values'][edit['key']][edit['row']]
                    edit['value']=row[edit['field']]+recipe['current_plus']
                else:raise AssertionError(recipe)
            assert type(edit['value']) is int and 0<=edit['value']<=NULL
        all_cases.append(m)
    return all_cases


def private_arithmetic_source():
    # Generic checker internals only; no generated packet header or raw fixture.
    return r'''/* PRIVATE/SYNTHETIC Stage04 controls, not public maximum capacity. */
#include "ir8_packet.c"
#include <stdio.h>
#include <stdlib.h>
static Ir8PacketWorkspace caller_workspace;
static Ir8PacketExpectedBindings bindings;
static unsigned failures;
#define CHECK(x) do { if (!(x)) { failures++; fprintf(stderr,"private control failed at %d\n",__LINE__); } } while(0)
static void clean_report(Ir8PacketReport *r) { report_init(r); }
static int early_report(const Ir8PacketReport *r,uint32_t status,uint32_t phase_id,uint32_t field,uint32_t detail) {
    return r->status==status && r->phase==phase_id && r->field==field && r->detail==detail &&
        r->domain==N && r->object==N && r->row==N && r->work_used==0 &&
        r->packet_bytes==0 && r->declared_packet_alignment==0 && r->member_bytes_sum==0 &&
        r->padding_bytes==0 && r->directory_entries==0 && r->member_objects==0 &&
        r->resolution_access_transport_rows==0 && r->workspace_bytes==0 &&
        r->graph_executed==0 && r->source_admitted==0 && r->runtime_admitted==0 && r->runtime_guards_executed==0;
}
int main(void) {
    Ir8PacketReport r; Check c={0}; uint32_t result=123, unchanged=123;
    unsigned char readable[sizeof(Ir8PacketProgramHeader)]={0};
    unsigned char destination[4]={1,2,3,4};
    unsigned char *large=(unsigned char *)calloc(1,UINT32_C(4194305));
    size_t i;
    if(!large)return 70;
    clean_report(&r);c.root=readable;c.bytes=sizeof readable;c.w=&caller_workspace;c.r=&r;
    CHECK(extent(&c,UINT32_MAX,1,&result)==1 && result==UINT32_MAX);
    CHECK(extent(&c,0,UINT32_MAX,&result)==1 && result==0);
    result=unchanged;
    CHECK(extent(&c,UINT32_MAX,2,&result)==0 && result==unchanged);
    CHECK(r.status==S(DIRECTORY) && r.detail==D(OVERFLOW));
    clean_report(&r);CHECK(charge(&c,IR8_PACKET_MAX_WORK)==1);
    CHECK(charge(&c,1)==0 && r.work_used==IR8_PACKET_MAX_WORK);
    CHECK(r.status==S(WORK_LIMIT) && r.detail==D(WORK_EXHAUSTED));
    clean_report(&r);r.work_used=IR8_PACKET_MAX_WORK-3;
    CHECK(copy(&c,0,4,destination)==0 && r.work_used==IR8_PACKET_MAX_WORK-3);
    CHECK(destination[0]==1 && destination[1]==2 && destination[2]==3 && destination[3]==4);
    CHECK(r.status==S(WORK_LIMIT) && r.detail==D(WORK_EXHAUSTED));
    /* Null report causes no access to any other argument. No invalid address. */
    memset(&caller_workspace,0xa5,sizeof caller_workspace);
    CHECK(ir8_packet_validate(NULL,0,NULL,NULL,NULL)==S(ARGUMENT));
    CHECK(ir8_packet_validate(NULL,0,&bindings,&caller_workspace,&r)==S(ARGUMENT));
    CHECK(early_report(&r,S(ARGUMENT),P(ARGUMENTS),0,D(NULL_ARGUMENT)));
    CHECK(ir8_packet_validate(readable,sizeof readable,NULL,&caller_workspace,&r)==S(ARGUMENT));
    CHECK(early_report(&r,S(ARGUMENT),P(ARGUMENTS),1,D(NULL_ARGUMENT)));
    CHECK(ir8_packet_validate(readable,sizeof readable,&bindings,NULL,&r)==S(ARGUMENT));
    CHECK(early_report(&r,S(ARGUMENT),P(ARGUMENTS),2,D(NULL_ARGUMENT)));
    for(i=0;i<sizeof caller_workspace;i++)CHECK(((unsigned char *)&caller_workspace)[i]==0xa5);
    CHECK(ir8_packet_validate(readable,sizeof readable-1,&bindings,&caller_workspace,&r)==S(HEADER));
    CHECK(early_report(&r,S(HEADER),P(HEADER_AND_SIZE),N,D(LENGTH)));
    CHECK(ir8_packet_validate(large,UINT32_C(4194305),&bindings,&caller_workspace,&r)==S(SIZE_LIMIT));
    CHECK(early_report(&r,S(SIZE_LIMIT),P(HEADER_AND_SIZE),N,D(LIMIT)));
    for(i=0;i<sizeof caller_workspace;i++)CHECK(((unsigned char *)&caller_workspace)[i]==0xa5);
    CHECK(ir8_packet_validate(large,UINT32_C(4194304),&bindings,&caller_workspace,&r)==S(HEADER));
    CHECK(r.phase==P(HEADER_AND_SIZE)&&r.detail==D(MAGIC)&&r.work_used>0);
    /* Actual directory cap gate; only a readable header is needed before the
       count check. At-cap proceeds to the expected missing extent rejection. */
    clean_report(&r);c.h.directory_count=16384;c.h.directory_offset=0;
    c.h.packet_alignment=(uint32_t)_Alignof(Ir8PacketProgramHeader);
    CHECK(check_directory(&c)==0 && r.status==S(DIRECTORY)&&r.detail==D(OFFSET));
    clean_report(&r);c.h.directory_count=16385;
    CHECK(check_directory(&c)==0 && r.status==S(COUNT_LIMIT)&&r.detail==D(LIMIT));
    printf("{\"format\":\"ir8-stage04-private-arithmetic/1\",\"failures\":%u,\"controls\":15,\"largest_readable_allocation\":4194305,\"public_capacity_claim\":false,\"raw_program_baselines\":0,\"graph_executed\":false}\n",failures);
    free(large);return failures?1:0;
}
'''


def generate_all(output):
    from resource_ir_v8.packet import loads_packet
    output=Path(output)
    if output.exists() or output.is_symlink():raise ValueError('fresh generation directory required')
    if not output.parent.is_dir() or output.parent.is_symlink():raise ValueError('safe existing parent required')
    output.mkdir()
    fixture_bytes=FIXTURE.read_bytes()
    assert hashlib.sha256(fixture_bytes).hexdigest()==DATA['stage03_fixture_sha256']
    fixtures={c['name']:c for c in json.loads(fixture_bytes)['cases']}
    summaries=[];total=0
    for candidate in DATA['native_fixtures']:
        name=candidate['name'];text=fixtures[name]['text'];payload=text.encode()
        assert len(payload)==candidate['raw_utf8_bytes'] and hashlib.sha256(payload).hexdigest()==candidate['raw_sha256']
        result=loads_packet(text);x=verify_emission(json.loads(text),result)
        mutations=make_mutations(name,x)
        directory=output/('%02d'%candidate['order']);directory.mkdir();files=[]
        control=dict(format='ir8-stage04-fixture-control/1',fixture=name,order=candidate['order'],raw_json=text,raw_sha256=candidate['raw_sha256'],expected={k:v for k,v in x.items() if k!='closure'},mutations=mutations,manifest_json=result.manifest_json,manifest_sha256=result.manifest_sha256,supplement_json=result.supplement_json,supplement_sha256=result.supplement_sha256)
        values=[('ir8_packet_generated.h',result.packet_header),('ir8_packet_generated.c',result.packet_source),('stage04_harness.c',source_harness(x,mutations)),('control.json',canon(control))]
        case_bytes=sum(len(content.encode('utf-8')) for _,content in values)
        if total+case_bytes>134217728:raise ValueError('generation evidence ceiling before write')
        for filename,content in values:exclusive(directory,filename,content,files)
        summary=dict(fixture=name,order=candidate['order'],files=list(files),expected_native_file='native.stdout.json',status='generated-uncompiled',raw_sha256=candidate['raw_sha256'],native_mutations=len(mutations),graph_executed=False,source_admitted=False)
        summaries.append(summary);total+=sum(f['bytes'] for f in files)
        if total>134217728:raise ValueError('generation evidence ceiling')
    arithmetic=private_arithmetic_source().encode('utf-8')
    if total+len(arithmetic)>134217728:raise ValueError('arithmetic source exceeds remaining evidence budget')
    with (output/'stage04_arithmetic.c').open('xb') as stream:stream.write(arithmetic)
    total+=len(arithmetic)
    manifest=dict(format='ir8-stage04-generation/1',private_arithmetic=dict(source='stage04_arithmetic.c',bytes=len(arithmetic),sha256=hashlib.sha256(arithmetic).hexdigest(),expected_native_file='arithmetic.stdout.json'),fixtures=summaries,files=50,payload_bytes_excluding_manifest=total,status='stop-for-generated-source-review',compiler_invoked=False,native_invoked=False)
    manifest_text=canon(manifest)
    if total+len(manifest_text.encode('utf-8'))>134217728:raise ValueError('generation manifest exceeds remaining evidence budget')
    with (output/'MANIFEST.json').open('x') as stream:stream.write(manifest_text)
    return manifest


def verify_all(index_path, receipt_directory):
    """Separately approved host invocation, no regeneration and no native launch."""
    index=json.loads(bounded_file(str(index_path),8388608));summaries=[]
    assert type(index) is dict
    exact(set(index),{'format','phase_plans','generation_manifest','fixtures','private_arithmetic'},'oracle index keys')
    exact(index['format'],'ir8-stage04-oracle-inputs/1','oracle input index')
    receipts=Path(receipt_directory)
    if not receipts.is_absolute() or '..' in receipts.parts or receipts.exists() or any(p.is_symlink() for p in (receipts,*receipts.parents)):raise ValueError('fresh absolute safe oracle output required')
    receipts.mkdir()
    def pinned(item,limit=67108864):
        assert type(item) is dict
        exact(set(item),{'path','bytes','sha256'},'input pin keys')
        if type(item['bytes']) is not int or not 0<=item['bytes']<=limit:raise ValueError('invalid declared pin size')
        if type(item['sha256']) is not str:raise ValueError('invalid declared pin hash')
        return bounded_file(item['path'],limit,item['bytes'],item['sha256'])
    planned={}
    assert type(index['phase_plans']) is list and 1<=len(index['phase_plans'])<=64
    for plan_item in index['phase_plans']:
        plan=json.loads(pinned(plan_item,8388608))
        exact(plan['schema'],'ir8-stage04-phase-plan/1','frozen phase plan schema')
        assert type(plan['commands']) is list and 1<=len(plan['commands'])<=64
        for command in plan['commands']:
            if command['id'] in planned:raise AssertionError('duplicate planned command id')
            planned[command['id']]=command
    assert len(planned)<=96
    checked_journals={}
    def journal(item,kind,stdout_item=None):
        payload=pinned(item,8388608)
        if item['sha256'] in checked_journals:
            command,result=checked_journals[item['sha256']]
        else:
            events=[json.loads(line) for line in payload.splitlines()]
            exact([e['event'] for e in events],['launch-intended','process-started','process-result'],'complete command journal')
            for event,keys in zip(events,({'event','command'},{'event','pid','pgid'},{'event','result'})):exact(set(event),keys,'journal event keys')
            command=events[0]['command'];exact(command,planned[command['id']],'exact planned command')
            started=events[1];assert type(started['pid']) is int and type(started['pgid']) is int and started['pid']>0 and started['pid']==started['pgid']
            result=events[2]['result']
            exact(set(result),{'schema','id','kind','status','launched','return_code','expected_return_code','execution_seconds','elapsed_seconds','abort','error','termination_actions','process_group_quiescent','streams_final','stream_bytes_observed','stream_bytes_saved','streams_truncated','receipt_write_error','streams'},'command result keys')
            exact(result['schema'],'ir8-stage04-contained-command/1','command result schema')
            exact(result['id'],command['id'],'result command identity')
            for key,value in dict(status='process-complete-expectation-pending',launched=True,return_code=0,expected_return_code=0,abort=None,error=None,termination_actions=[],process_group_quiescent=True,streams_final=True,streams_truncated=False,receipt_write_error=None).items():exact(result[key],value,'command result '+key)
            exact(result['kind'],command['kind'],'result kind');exact(command['expected_return_code'],0,'planned return code')
            import math
            assert type(result['execution_seconds']) in (int,float) and math.isfinite(result['execution_seconds']) and 0<=result['execution_seconds']<=command['limits']['wall_seconds']
            exact(result['elapsed_seconds'],result['execution_seconds'],'command elapsed duration')
            for key in ('stream_bytes_observed','stream_bytes_saved','streams'):exact(set(result[key]),{'stdout','stderr'},'stream result keys')
            exact(result['stream_bytes_observed'],result['stream_bytes_saved'],'complete captured streams')
            for label in ('stdout','stderr'):
                exact(set(result['streams'][label]),{'bytes','sha256'},'stream identity keys')
                assert type(result['stream_bytes_saved'][label]) is int and result['stream_bytes_saved'][label]>=0
                stream_path=Path(item['path']).parent/(label+'.raw')
                stream_item=dict(path=str(stream_path),bytes=result['streams'][label]['bytes'],sha256=result['streams'][label]['sha256'])
                pinned(stream_item,command['limits'][label+'_bytes'])
                exact(stream_item['bytes'],result['stream_bytes_saved'][label],'stream byte count')
            checked_journals[item['sha256']]=(command,result)
        exact(command['kind'],kind,'requested command kind')
        if stdout_item is not None:
            exact(Path(stdout_item['path']),Path(item['path']).parent/'stdout.raw','exact stdout artifact path')
            exact(stdout_item['bytes'],result['streams']['stdout']['bytes'],'stdout receipt bytes')
            exact(stdout_item['sha256'],result['streams']['stdout']['sha256'],'stdout receipt hash')
        return command
    def argument_paths(command):
        return [str((Path(command['cwd'])/v).resolve()) for v in command['argv'][1:] if not v.startswith('-')]
    manifest=json.loads(pinned(index['generation_manifest'],8388608))
    exact(manifest['format'],'ir8-stage04-generation/1','generation manifest format')
    exact(manifest['files'],50,'finite generation file count')
    exact([f['name'] for f in index['fixtures']],[f['name'] for f in DATA['native_fixtures']],'pinned fixture names')
    def symbols(payload,packet_bytes):
        import re
        rows=[]
        for line in payload.decode('ascii').splitlines():
            match=re.fullmatch(r'([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([A-Za-z])\s+([A-Za-z_][A-Za-z0-9_]*)',line.strip())
            if not match:raise AssertionError(('unexpected nm line',line))
            rows.append((match[4],match[3],int(match[2],16)))
        exact(sorted(name for name,kind,size in rows),sorted(('ir8_packet_generated_root','ir8_packet_generated_data','ir8_packet_generated_size')),'production object symbols')
        for name,kind,size in rows:
            if name=='ir8_packet_generated_root':
                assert kind=='r' and size==packet_bytes,'exact immutable root symbol'
            else:assert kind=='T' and size>0,'fixed getter text symbol'
        return rows
    exact(len(manifest['fixtures']),12,'fixed native fixture count')
    for candidate,generated,inputs in zip(DATA['native_fixtures'],manifest['fixtures'],index['fixtures']):
        directory=Path(inputs['generation_directory'])
        if type(inputs['generation_directory']) is not str or not directory.is_absolute() or str(directory)!=inputs['generation_directory'] or '..' in directory.parts or any(p.is_symlink() for p in (directory,*directory.parents)):raise ValueError('unsafe generation input')
        exact(inputs['control']['path'],str(directory/'control.json'),'control input path')
        control_bytes=pinned(inputs['control'],33554432)
        control=json.loads(control_bytes)
        exact(control['fixture'],candidate['name'],'control fixture')
        for key in ('packet_object','executable'):pinned(inputs[key])
        compile_command=journal(inputs['compiler_receipt'],'compiler')
        native_command=journal(inputs['native_receipt'],'native-packet',inputs['native_stdout'])
        inspect_command=journal(inputs['inspection_receipt'],'inspection',inputs['packet_nm'])
        exact(native_command['argv'],[inputs['executable']['path']],'native executable association')
        exact(native_command['executable_record']['sha256'],inputs['executable']['sha256'],'launched executable hash')
        exact(native_command['executable_record']['bytes'],inputs['executable']['bytes'],'launched executable bytes')
        exact(inspect_command['argv'][1:],['-S','--defined-only',inputs['packet_object']['path']],'production object inspection argv')
        associations=dict(production_object=inputs['packet_object']['path'],executable=inputs['executable']['path'],production_source=str(directory/'ir8_packet_generated.c'),harness_source=str(directory/'stage04_harness.c'))
        exact(compile_command['artifacts'],associations,'compiler artifact associations')
        paths=argument_paths(compile_command)
        assert associations['production_source'] in paths and associations['harness_source'] in paths
        argv=compile_command['argv'];assert argv.count('-o')==1
        exact(str((Path(compile_command['cwd'])/argv[argv.index('-o')+1]).resolve()),associations['executable'],'compiler output argv')
        exact(generated['fixture'],candidate['name'],'fixture identity')
        exact([member['name'] for member in generated['files']],['ir8_packet_generated.h','ir8_packet_generated.c','stage04_harness.c','control.json'],'exact generated file inventory')
        for member in generated['files']:
            exact(set(member),{'name','bytes','sha256'},'generated file pin keys')
            payload=pinned(dict(path=str(directory/member['name']),bytes=member['bytes'],sha256=member['sha256']),33554432)
            if member['name']=='control.json':exact(payload,control_bytes,'control identity')
        raw_text=control['raw_json'];assert type(raw_text) is str
        exact(len(raw_text.encode()),candidate['raw_utf8_bytes'],'raw length')
        exact(hashlib.sha256(raw_text.encode()).hexdigest(),candidate['raw_sha256'],'raw bytes')
        native_bytes=pinned(inputs['native_stdout'],33554432)
        native=json.loads(native_bytes)
        assert type(native) is dict
        exact(set(native),{'baseline','controls','support','harness_failures'},'native output keys')
        support=verify_support(native['support'],native['baseline'])
        receipt=verify_native(json.loads(raw_text),native['baseline'],support)
        receipt['harness_support_bytes']=support
        receipt['production_symbols']=symbols(pinned(inputs['packet_nm'],4194304),receipt['packet_bytes'])
        exact(native['harness_failures'],0,'harness failures')
        mutation_specs=control['mutations']
        expected_names=['repeat-original','byte-aligned-copy']+[m['name'] for m in mutation_specs]
        exact([c['name'] for c in native['controls']],expected_names,'finite control inventory')
        for control in native['controls'][:2]:
            exact(set(control),{'name','status','report'},'repeat control keys')
            exact(control['status'],0,'fresh validation')
            verify_report(control['report'],control['status'],support)
            exact(control['report'],native['baseline']['report'],'repeat complete report')
        outcomes=[]
        for spec,actual in zip(mutation_specs,native['controls'][2:]):
            keys={'name','status','report','readback'} if spec.get('correspondence_reject') else {'name','status','report'}
            exact(set(actual),keys,'mutation output keys')
            verify_report(actual['report'],actual['status'],support)
            if spec.get('correspondence_reject'):
                exact(actual['status'],0,'coherent structural acceptance')
                exact(actual['readback']['report'],actual['report'],'coherent readback report')
                try:verify_native(json.loads(raw_text),actual['readback'],support)
                except AssertionError as error:
                    failure=error.args[0] if error.args else 'unspecified'
                    expected_key='table/sites' if spec['name']=='coherent-nullary-variant-switch' else 'pool/strings'
                    if type(failure) is not tuple or not str(failure[0]).startswith(expected_key):raise
                    outcomes.append(dict(name=spec['name'],native_status=0,oracle='rejected-after-full-fresh-readback',mismatch=list(failure)))
                else:raise AssertionError('independent oracle accepted coherent tampering')
            else:
                if spec.get('expected_diagnostic') is None:raise AssertionError('unfrozen diagnostic blocks qualification')
                fields=('status','phase','domain','object','row','field','detail')
                exact({f:actual['report'][f] for f in fields},spec['expected_diagnostic'],'mutation '+spec['name'])
                outcomes.append(dict(name=spec['name'],native_status=actual['status'],diagnostic=spec['expected_diagnostic']))
        receipt.update(fixture=candidate['name'],native_stdout_sha256=hashlib.sha256(native_bytes).hexdigest(),controls=len(native['controls']),mutation_outcomes=outcomes)
        summaries.append(receipt)
    arithmetic_inputs=index['private_arithmetic'];pinned(arithmetic_inputs['executable'])
    arithmetic_compile=journal(arithmetic_inputs['compiler_receipt'],'compiler')
    arithmetic_native=journal(arithmetic_inputs['native_receipt'],'native-arithmetic',arithmetic_inputs['native_stdout'])
    exact(arithmetic_native['argv'],[arithmetic_inputs['executable']['path']],'private arithmetic executable')
    exact(arithmetic_native['executable_record']['sha256'],arithmetic_inputs['executable']['sha256'],'private arithmetic binary hash')
    exact(arithmetic_native['executable_record']['bytes'],arithmetic_inputs['executable']['bytes'],'private arithmetic binary bytes')
    arithmetic_source=str(Path(index['generation_manifest']['path']).parent/'stage04_arithmetic.c')
    exact(arithmetic_compile['artifacts'],dict(executable=arithmetic_inputs['executable']['path'],source=arithmetic_source),'private arithmetic compiler artifacts')
    assert arithmetic_source in argument_paths(arithmetic_compile)
    arithmetic_argv=arithmetic_compile['argv'];assert arithmetic_argv.count('-o')==1
    exact(str((Path(arithmetic_compile['cwd'])/arithmetic_argv[arithmetic_argv.index('-o')+1]).resolve()),arithmetic_inputs['executable']['path'],'private arithmetic output argv')
    source_identity=manifest['private_arithmetic']
    pinned(dict(path=arithmetic_source,bytes=source_identity['bytes'],sha256=source_identity['sha256']))
    arithmetic=json.loads(pinned(arithmetic_inputs['native_stdout'],4194304))
    exact(arithmetic,dict(format='ir8-stage04-private-arithmetic/1',failures=0,controls=15,largest_readable_allocation=4194305,public_capacity_claim=False,raw_program_baselines=0,graph_executed=False),'private arithmetic result')
    with (receipts/'CORRESPONDENCE.json').open('x') as stream:stream.write(canon(dict(format='ir8-stage04-correspondence/1',fixtures=summaries,status='packet-only-correspondence-passed',runtime_total_static_bytes=None,graph_executed=False,source_admitted=False)))
    return summaries


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('generate','verify'));parser.add_argument('path');parser.add_argument('--output');args=parser.parse_args()
    if args.mode=='verify' and args.output is None:parser.error('verify requires --output for fresh receipt directory')
    result=generate_all(args.path) if args.mode=='generate' else verify_all(args.path,args.output)
    print(canon(result))
