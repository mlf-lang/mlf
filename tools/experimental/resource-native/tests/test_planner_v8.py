"""Synthetic/raw fragment lowering tests, NOT genuine K/source acceptance.

The unchanged independent IR8 checker and emitter consume actual planner output.
No source compiler or evaluator is mocked, run, or credited by these tests.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import planner_v8 as p
import module_shared_transport as transport
from resource_ir_v8.checker import check_resources
from resource_ir_v8.runtime_emit import emit_runtime

I = {'tag':'constructor','name':'Int','arguments':[]}
B = {'tag':'constructor','name':'Bool','arguments':[]}


def name(i): return {'id':i,'hint':'v'+str(i)}
def var(i): return {'tag':'var','name':name(i)}
def lit(i=42): return {'tag':'int64','value':i}
def boolean(b=True): return {'tag':'bool','value':b}
def ty(i): return {'tag':'var','id':i}
def arr(a,b): return {'tag':'arrow','from':a,'to':b}
def lam(i,t,body): return {'tag':'lambda','parameter':name(i),'parameter_type':t,'body':body}
def let(i,value,body): return {'tag':'let','name':name(i),'value':value,'body':body}
def app(f,x): return {'tag':'application','function':f,'argument':x}
def prefix(ids,body):
    for i in reversed(ids): body={'tag':'type_lambda','id':i,'bound':{'tag':'bottom'},'body':body}
    return body
def use(i,*arguments):
    out=var(i)
    for t in arguments:
        out={'tag':'type_application','value':out,'witness':{'tag':'then',
             'first':{'tag':'inner','witness':{'tag':'bottom','type':t}},'second':{'tag':'elim'}}}
    return out
def prim(code,label,*args):
    out={'tag':'primitive','id':code,'name':label,'arguments':[I] if code==13 else []}
    for arg in args: out=app(out,arg)
    return out
def add(a,b): return prim(8,'addInt',a,b)
def choose(c,a,b): return prim(13,'ifThenElse',c,a,b)


def pending_shared():
    # Three actual lambdas, two applications and one ordinary let. No planner
    # admission rule depends on these counts or on any binder's display name.
    a=ty(100)
    rhs=app(lam(2,arr(a,a),var(2)),lam(3,a,let(4,app(lam(5,a,var(5)),var(3)),var(4))))
    return let(1,prefix([100],rhs),add(app(use(1,I),lit(41)),choose(app(use(1,B),boolean()),lit(1),lit(0))))


def nested_pair_capture():
    a=ty(100)
    carrier=lam(3,I,lam(4,B,app(use(1,I),var(3))))
    return let(1,prefix([100],lam(2,a,var(2))),app(app(carrier,lit()),boolean()))


def dead_vector_capture():
    carrier=lam(3,I,add(app(use(1,I,I),lit(1)),app(use(1,I,B),lit(2))))
    return let(1,prefix([100,101],lam(2,ty(100),var(2))),app(carrier,lit(0)))


def curried_shared():
    rhs=lam(2,ty(100),lam(3,ty(101),var(2)))
    body=let(4,app(use(1,I,B),lit()),let(5,app(use(1,B,I),boolean()),
             choose(app(var(5),lit(0)),app(var(4),boolean(False)),lit(0))))
    return let(1,prefix([100,101],rhs),body)


def unselected_arithmetic():
    return let(1,prefix([100],lam(2,ty(100),var(2))),
               choose(boolean(),app(use(1,I),lit()),add(lit(123),lit(456))))


def nominal(name_): return {'tag':'constructor','name':name_,'arguments':[]}
def field_type(t):
    if t['tag']=='arrow': return {'tag':'function','from':field_type(t['from']),'to':field_type(t['to'])}
    return {'tag':'applied','name':t['name'],'arguments':[]}
def declaration(type_name,ctor,*fields):
    return {'tag':'data_kind','name':type_name,'parameters':[],
            'constructors':[{'name':ctor,'fields':[field_type(t) for t in fields]}]}
def with_data(declarations,body): return {'tag':'with_data','declarations':declarations,'body':body}
def construct(ctor,*args):
    node={'tag':'constructor','name':ctor,'arguments':[]}
    for arg in args: node=app(node,arg)
    return node
def data_case(value,ctor,binders,body,result=I):
    return {'tag':'case','scrutinee':value,'result_type':result,
            'alternatives':[{'pattern':{'tag':'constructor','constructor':ctor,
                                        'fields':[None if n is None else name(n) for n in binders]},'body':body}]}
def scalar_box():
    return with_data([declaration('Box','BoxValue',I)],
                     let(1,construct('BoxValue',lit()),data_case(var(1),'BoxValue',[2],var(2))))
def callable_box():
    pending=app(lam(3,arr(I,I),var(3)),use(1,I))
    return with_data([declaration('FnBox','FnBoxValue',arr(I,I))],
        let(1,prefix([100],lam(2,ty(100),var(2))),
            let(4,construct('FnBoxValue',pending),
                let(5,data_case(var(4),'FnBoxValue',[6],var(6),arr(I,I)),
                    choose(app(use(1,B),boolean()),app(var(5),lit()),lit(0))))))
def curried_box():
    return with_data([declaration('FnBox','FnBoxValue',arr(B,I))],
        let(1,prefix([100,101],lam(2,ty(100),lam(3,ty(101),var(2)))),
            let(4,construct('FnBoxValue',app(use(1,I,B),lit())),
                let(5,data_case(var(4),'FnBoxValue',[6],var(6),arr(B,I)),
                    choose(app(app(use(1,B,I),boolean()),lit(7)),app(var(5),boolean(False)),lit(0))))))
def wildcard_box():
    return with_data([declaration('PairBox','PairValue',I,I)],
        let(1,prefix([100],lam(2,ty(100),var(2))),
            data_case(construct('PairValue',app(use(1,I),lit()),app(use(1,I),lit(999))),
                      'PairValue',[3,None],var(3))))


def instructions(program):
    out=[]
    def walk(body):
        for x in body:
            out.append(x)
            if x['op']=='generalize': walk(x['body'])
    walk(program['entry'])
    for key in ('functions','codes'):
        for c in program[key].values(): walk(c['body'])
    return out


class PlannerTests(unittest.TestCase):
    def checked(self,raw):
        before=copy.deepcopy(raw); planned=p.plan_fragment(raw)
        self.assertEqual(raw,before)
        self.assertFalse(planned['binding']['source_admitted'])
        self.assertFalse(planned['binding']['ordinary_K_checked'])
        self.assertEqual(planned['binding']['status'],'candidate-not-resource-checked')
        check_resources(planned['program'])
        return planned

    def test_pending_rhs_preserves_graph_once_and_full_source_coverage(self):
        r=self.checked(pending_shared()); program=r['program']; ops=instructions(program)
        self.assertEqual(len(program['schemes']),1)
        self.assertEqual(len(program['functions']),3)
        self.assertEqual(sum(x['op']=='generalize' for x in ops),1)
        generic=[x for x in ops if x['op']=='generalize'][0]['body']
        self.assertEqual(sum(x['op']=='application' for x in generic),1)
        pending=[x['out'] for x in generic if x['op']=='application'][0]
        self.assertEqual(generic[-1],{'op':'seal','value':pending})
        self.assertFalse(any(x['op']=='force' for x in generic))
        scoped=[c for c in program['functions'].values() if c['type_scope'] is not None]
        self.assertEqual(len(scoped),3)
        self.assertEqual(sum(x['op']=='application' for c in scoped for x in c['body']),1)
        self.assertEqual(len(r['binding']['source_map']['scheme_map']),1)
        self.assertEqual(len(r['binding']['source_map']['use_map']),2)

    def test_nested_carrier_reuses_saved_view_without_reinstantiate(self):
        r=self.checked(nested_pair_capture()); program=r['program']
        pairs=[x for c in r['binding']['source_map']['carrier_map'] for x in c['view_captures']]
        self.assertEqual(len(pairs),2)
        self.assertEqual([x['source_view']['kind'] for x in pairs],['scheme','captured'])
        self.assertEqual(pairs[0]['arguments'],pairs[1]['arguments'])
        self.assertEqual(sum(x['op']=='instantiate' for x in instructions(program)),1)
        self.assertEqual(len(program['functions']),3)
        for c in program['functions'].values():
            self.assertTrue(all(v['relation']=='down' for v in c['captures'].values()))

    def test_dead_parameter_remains_distinct_view_capture(self):
        r=self.checked(dead_vector_capture()); program=r['program']
        self.assertEqual(next(iter(program['schemes'].values()))['parameters'],2)
        self.assertEqual(len(program['instantiations']),2)
        vectors=[v['arguments'] for v in program['instantiations'].values()]
        self.assertEqual(vectors[0][0],vectors[1][0]);self.assertNotEqual(vectors[0][1],vectors[1][1])
        carrier=next(c for c in r['binding']['source_map']['carrier_map'] if c['kind']=='lambda' and len(c['view_captures'])==2)
        self.assertEqual(len({x['capture'] for x in carrier['view_captures']}),2)
        self.assertEqual(carrier['view_captures'][0]['layout'],carrier['view_captures'][1]['layout'])

    def test_real_curried_capture_keeps_symbolic_type_and_one_body(self):
        r=self.checked(curried_shared()); program=r['program']
        scoped=[c for c in program['functions'].values() if c['type_scope'] is not None]
        self.assertEqual(len(scoped),2)
        captured=next(c for c in scoped if c['captures'])
        self.assertEqual(len(captured['captures']),1)
        layout=next(iter(captured['captures'].values()))['layout']
        self.assertEqual(program['types'][layout[1:]],{'tag':'rigid','scheme':'S0','index':0})
        self.assertEqual(len(program['instantiations']),2)

    def test_genuine_runtime_source_emitter_accepts_fragment_programs(self):
        for raw in (pending_shared(),nested_pair_capture(),dead_vector_capture(),curried_shared()):
            with self.subTest(raw=raw['body']['tag']):
                program=self.checked(raw)['program']; emission=emit_runtime(program)
                self.assertEqual(json.loads(emission.canonical_ir_json),program)
                self.assertIn('rt8_generic_begin(',emission.runtime_source)
                self.assertIn('rt8_instantiate(',emission.runtime_source)

    def test_no_argument_identity_inference(self):
        program=self.checked(let(1,prefix([100],lam(2,ty(100),var(2))),app(use(1,I),lit())))['program']
        self.assertTrue(all(x['result_identity']=='unknown' and x['protocol']=='repeat' for x in program['signatures'].values()))
        self.assertTrue(all(x.get('result_identity','unknown')=='unknown' for x in program['types'].values()))

    def test_same_display_hint_distinct_actual_binders(self):
        raw=let(1,prefix([100],lam(2,ty(100),var(2))),
                let(3,prefix([200],lam(4,ty(200),var(4))),
                    app(lam(5,I,add(app(use(1,I),lit(1)),app(use(3,I),lit(2)))),lit(0))))
        def hints(n):
            if isinstance(n,dict):
                if set(n)=={'id','hint'} and n['id'] in (1,3):n['hint']='same'
                for v in n.values():hints(v)
            elif isinstance(n,list):
                for v in n:hints(v)
        hints(raw);r=self.checked(raw)
        pairs=next(c['view_captures'] for c in r['binding']['source_map']['carrier_map'] if len(c['view_captures'])==2)
        self.assertEqual({x['binder'] for x in pairs},{1,3})
        self.assertEqual(len(r['program']['schemes']),2)

    def test_claimed_fragment_is_freshly_replayed(self):
        raw=pending_shared(); fragment=transport.derive_shared_fragment(raw)
        fragment['polymorphism']['uses'][0]['arguments']=[B]
        with self.assertRaises(transport.SharedTransportError):p.plan_fragment(raw,fragment=fragment)

    def test_primitive_spine_maps_and_conditional_delay(self):
        raw=unselected_arithmetic();r=self.checked(raw);maps=r['binding']['source_map']
        self.assertEqual(sum(x['role']=='primitive-spine' for x in maps['term_map']),5)
        self.assertEqual(sum(x['role']=='primitive' for x in maps['term_map']),2)
        ordinary=[x for x in maps['allocation_map'] if x['role']=='application']
        self.assertEqual(len(ordinary),1)
        source=raw
        for key in ordinary[0]['source']['path']:source=source[key]
        self.assertEqual(source['function']['tag'],'type_application')
        outer=next(x for x in maps['carrier_map'] if x['kind']=='conditional')
        branches=[x for x in maps['carrier_map'] if x['kind'] in ('conditional-then','conditional-else')]
        self.assertEqual(len(branches),2)
        body=r['program']['codes'][outer['ir_code']]['body']
        self.assertEqual(sum(x['op']=='force' for x in body),1) # condition only
        self.assertEqual(sum(x['op']=='thunk' for x in body),2) # whole alternatives
        self.assertEqual(sum(x['op']=='select_i64' for x in body),1)
        self.assertFalse(any(x['op']=='prim2' for x in body))
        bad=copy.deepcopy(raw)
        # The false branch is unselected at run time, but its whole syntax still
        # undergoes fresh proof/type admission. No constant-folding escape.
        head=bad['body']['argument']['function']['function']
        self.assertEqual(head['tag'],'primitive');head['id']=9999
        with self.assertRaises(transport.SharedTransportError):p.plan_fragment(bad)

    def test_unsupported_bare_partial_open_external_and_recursive_reject(self):
        cases=[let(1,prefix([100],lam(2,ty(100),var(2))),var(1)),
               let(1,prefix([100,101],lam(2,ty(100),var(2))),use(1,I)),
               let(1,prefix([100],lam(2,ty(100),var(2))),use(1,ty(999))),
               let(9,lit(),let(1,prefix([100],lam(2,ty(100),var(9))),app(use(1,I),lit()))),
               {'tag':'letrec','bindings':[{'name':name(1),'type':I,'value':var(1)}],'body':var(1)},
               {'tag':'constructor','name':'()','arguments':[]}]
        for raw in cases:
            with self.subTest(raw=raw['tag']),self.assertRaises((transport.SharedTransportError,p.PlanningError)):
                p.plan_fragment(raw)

    def test_planner_work_limit_is_fail_closed(self):
        raw=nested_pair_capture(); old=p.MAX_WORK
        try:
            p.MAX_WORK=1
            with self.assertRaises(p.PlanningError):p.plan_fragment(raw)
        finally:p.MAX_WORK=old

    def test_scalar_data_whole_case_is_delayed_with_exact_loan_order(self):
        r=self.checked(scalar_box()); program=r['program']; maps=r['binding']['source_map']
        self.assertEqual(len(program['layouts']),1)
        self.assertEqual(len(maps['constructor_map']),1)
        self.assertEqual(sum(x['role']=='constructor-spine' for x in maps['term_map']),1)
        self.assertFalse(any(x['role']=='application' for x in maps['allocation_map']))
        case=maps['case_map'][0]; body=program['codes'][case['code']]['body']
        ops=[x['op'] for x in body]
        self.assertEqual(ops[:6],['retain','force','field','retain','end_borrow','drop'])
        self.assertEqual(ops.count('force'),1)
        self.assertFalse(any(x['op']=='field' for x in program['entry']))
        self.assertIn(['body','body','alternatives','0','body'],[x['source']['path'] for x in maps['term_map']])

    def test_data_arrow_case_preserves_pending_payload_and_both_views(self):
        r=self.checked(callable_box()); program=r['program']; maps=r['binding']['source_map']
        self.assertEqual(len(program['schemes']),1);self.assertEqual(len(program['functions']),2)
        self.assertEqual(len(program['instantiations']),2)
        alloc=next(x for x in program['entry'] if x['op']=='alloc')
        pending=next(x for x in program['entry'] if x['op']=='application')
        self.assertEqual(alloc['fields'],{'f0':pending['out']})
        self.assertFalse(any(x['op']=='force' for x in program['entry'][:program['entry'].index(alloc)]))
        typ=program['types'][maps['case_map'][0]['result_type']]
        self.assertEqual((typ['tag'],typ['protocol'],typ['result_identity']),('arrow','repeat','unknown'))
        case=program['codes'][maps['case_map'][0]['code']]
        self.assertFalse(any(x['op']=='application' for x in case['body']))
        self.assertEqual(case['result'],'^'+maps['case_map'][0]['result_type'])

    def test_data_curried_field_keeps_full_vector_and_real_capture(self):
        r=self.checked(curried_box()); program=r['program']
        self.assertEqual(next(iter(program['schemes'].values()))['parameters'],2)
        self.assertEqual({tuple(x['arguments']) for x in program['instantiations'].values()},
                         {tuple(reversed(x['arguments'])) for x in program['instantiations'].values()})
        scoped=[f for f in program['functions'].values() if f['type_scope'] is not None]
        self.assertEqual(len(scoped),2);self.assertEqual(sum(len(f['captures']) for f in scoped),1)
        self.assertEqual(sum(x['op']=='alloc' for x in instructions(program)),1)

    def test_data_wildcard_keeps_both_pending_payload_graphs_without_demand(self):
        r=self.checked(wildcard_box()); program=r['program']; maps=r['binding']['source_map']
        case=program['codes'][maps['case_map'][0]['code']]['body']
        self.assertEqual(sum(x['op']=='application' for x in case),2)
        self.assertEqual(sum(x['op']=='force' for x in case),1)
        self.assertEqual(sum(x['op']=='field' for x in case),1)
        alloc=next(x for x in case if x['op']=='alloc')
        self.assertEqual(set(alloc['fields']),{'f0','f1'})
        self.assertEqual(len(maps['use_map']),2)
        self.assertTrue(all(x['op']!='force' for x in case[:case.index(alloc)]))

    def test_data_brands_do_not_merge_equal_fields(self):
        declarations=[declaration('A','MkA',I),declaration('B','MkB',I)]
        raw=with_data(declarations,let(1,construct('MkA',lit()),
                let(2,construct('MkB',lit(7)),data_case(var(1),'MkA',[3],var(3)))))
        r=self.checked(raw); layouts=r['program']['layouts']
        self.assertEqual(len(layouts),2);self.assertEqual(layouts['D0'],layouts['D1'])
        self.assertEqual([x['declaration'] for x in r['binding']['source_map']['nominal_map']],[0,1])
        bad=with_data(declarations,app(lam(1,nominal('A'),lit()),construct('MkB',lit())))
        with self.assertRaises(transport.SharedTransportError):p.plan_fragment(bad)

    def test_data_case_arm_capture_keeps_view_pairs_and_local_pattern_scope(self):
        raw=with_data([declaration('Box','MkBox',I)],
            let(1,prefix([100],lam(2,ty(100),var(2))),
                app(data_case(construct('MkBox',lit(41)),'MkBox',[3],
                              lam(4,B,add(var(3),app(use(1,I),lit(1)))),arr(B,I)),boolean())))
        r=self.checked(raw); carriers=r['binding']['source_map']['carrier_map']
        case=next(c for c in carriers if c['kind']=='data-case')
        self.assertEqual(case['mono_captures'],[])
        self.assertEqual(len(case['view_captures']),1)
        inner=next(c for c in carriers if c['kind']=='lambda' and c['type_scope'] is None)
        self.assertEqual(inner['mono_captures'][0]['binder'],3)
        self.assertEqual(inner['view_captures'][0]['source_view']['kind'],'captured')

    def test_data_source_emitter_uses_real_existing_helpers(self):
        for raw in (scalar_box(),callable_box(),curried_box(),wildcard_box()):
            emission=emit_runtime(self.checked(raw)['program'])
            self.assertIn('rt8_alloc(',emission.runtime_source)
            self.assertIn('rt8_field(',emission.runtime_source)
            self.assertIn('rt8_end_borrow(',emission.runtime_source)
            self.assertNotIn('rt8_case_fields_i64(',emission.runtime_source)

    def test_data_unsupported_shapes_and_patterns_reject(self):
        good=scalar_box(); bad=[]
        partial=copy.deepcopy(good);partial['body']['value']=partial['body']['value']['function'];bad.append(partial)
        wrong=copy.deepcopy(good);wrong['body']['value']['argument']=boolean();bad.append(wrong)
        pattern=copy.deepcopy(good);pattern['body']['body']['alternatives'][0]['pattern']['constructor']='Absent';bad.append(pattern)
        arity=copy.deepcopy(good);arity['body']['body']['alternatives'][0]['pattern']['fields']=[];bad.append(arity)
        params=copy.deepcopy(good);params['declarations'][0]['parameters']=[{'name':'a','kind':{'tag':'star'}}];bad.append(params)
        recursive=copy.deepcopy(good);recursive['declarations'][0]['constructors'][0]['fields']=[field_type(nominal('Box'))];bad.append(recursive)
        many=copy.deepcopy(good);many['declarations'][0]['constructors'].append({'name':'Other','fields':[]});bad.append(many)
        opened=copy.deepcopy(good);opened['declarations'][0]['constructors'][0]['fields']=[{'tag':'parameter','name':'a'}];bad.append(opened)
        generic=with_data([declaration('Box','MkBox',I)],let(1,prefix([100],lam(2,ty(100),
            let(3,construct('MkBox',lit()),var(2)))),app(use(1,I),lit())))
        bad.append(generic)
        for raw in bad:
            with self.subTest(raw=raw),self.assertRaises((transport.SharedTransportError,p.PlanningError)):
                p.plan_fragment(raw)

    @unittest.skipUnless(os.environ.get('IR8_PLANNER_NATIVE')=='1',
                         'opt-in genuine C/native fragment tests')
    def test_native_fragments(self):
        """Real callbacks, no stubs; still no genuine source/K qualification.

        IR8_PLANNER_NATIVE_OUTPUT may name a NEW directory to retain raw inputs,
        generated sources, actual argv and compiler/native streams. Otherwise
        unittest uses a temporary directory. No old evidence is overwritten.
        """
        compiler=shutil.which(os.environ.get('CC','gcc-14'))
        self.assertIsNotNone(compiler,'an existing C11 compiler is required')
        self.assertEqual(os.name,'posix','resource limits require POSIX')
        import resource
        destination=os.environ.get('IR8_PLANNER_NATIVE_OUTPUT')
        if destination:
            output=Path(destination).resolve();output.mkdir()
        else:
            temporary=tempfile.TemporaryDirectory(prefix='ir8-planner-fragments-')
            self.addCleanup(temporary.cleanup);output=Path(temporary.name)
        def limits():
            resource.setrlimit(resource.RLIMIT_CPU,(20,20))
            resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
            resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
        cases=(('pending',pending_shared,42),('nested-capture',nested_pair_capture,42),
               ('dead-vector',dead_vector_capture,3),('curried',curried_shared,42),
               ('unselected-arithmetic',unselected_arithmetic,42))
        for name,make,expected in cases:
            with self.subTest(case=name):
                directory=output/name;directory.mkdir();raw=make();plan=self.checked(raw)
                (directory/'raw-fragment.json').write_text(json.dumps(raw,indent=2)+'\n')
                (directory/'planned.json').write_text(json.dumps(plan,indent=2)+'\n')
                emission=emit_runtime(plan['program'])
                for filename,field in (('ir8_packet_generated.h','packet_header'),('ir8_packet_generated.c','packet_source'),
                                       ('ir8_runtime_generated.h','runtime_header'),('ir8_runtime_generated.c','runtime_source')):
                    (directory/filename).write_text(getattr(emission,field))
                argv=[compiler,'-std=c11','-O0','-g','-Wall','-Wextra','-Werror','-pedantic',
                      '-I'+str(BASE/'packet_v8'),'-I'+str(BASE/'runtime_v8'),'-I'+str(directory),
                      str(BASE/'packet_v8/ir8_packet.c')]
                argv += [str(BASE/'runtime_v8'/f) for f in ('rir8_binding.c','rir8_guard.c','rir8_memory.c',
                           'rir8_runtime.c','rir8_force.c','rir8_session.c')]
                argv += [str(directory/'ir8_packet_generated.c'),str(directory/'ir8_runtime_generated.c'),
                         str(BASE/'tests/stage05_runtime_driver.c'),'-o',str(directory/'native')]
                (directory/'command.json').write_text(json.dumps(argv,indent=2)+'\n')
                with (directory/'compile.stdout').open('xb') as out,(directory/'compile.stderr').open('xb') as err:
                    compiled=subprocess.run(argv,stdout=out,stderr=err,timeout=60,preexec_fn=limits)
                self.assertEqual(compiled.returncode,0,(directory/'compile.stderr').read_text())
                with (directory/'run.stdout').open('xb') as out,(directory/'run.stderr').open('xb') as err:
                    native=subprocess.run([str(directory/'native')],stdout=out,stderr=err,timeout=20,preexec_fn=limits)
                self.assertEqual(native.returncode,0,(directory/'run.stderr').read_text())
                self.assertEqual((directory/'run.stderr').read_bytes(),b'')
                report=json.loads((directory/'run.stdout').read_text())['evaluation']
                self.assertEqual(report['fault'],0)
                self.assertEqual(report['scalar_result'],expected)
                self.assertEqual(report['metrics']['entries_completed'],1)
                if name=='unselected-arithmetic':
                    self.assertFalse(any(e.get('primitive')=='addInt' for e in report['events']))
                    scalar_values=[e['value'] for e in report['events'] if e['event']=='scalar_value']
                    self.assertNotIn(123,scalar_values);self.assertNotIn(456,scalar_values)
                for row in [report['memory']]+list(report['memory_categories'].values()):
                    self.assertEqual(row['live_bytes'],0)
                    self.assertEqual(row['live_blocks'],0)


if __name__=='__main__':unittest.main()
