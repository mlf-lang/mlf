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
