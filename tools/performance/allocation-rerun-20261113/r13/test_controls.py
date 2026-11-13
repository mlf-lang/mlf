import types
import json,sys,time,threading
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import controls

def row(label,n,parents=()):return {'self_alloc':n,'stack':[{'label':x} for x in [*parents,label]]}
class ControlTests(unittest.TestCase):
    def test_fixture_uses_common_interface_helper(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'Fixture.hs';source.write_text('module Main where\nmain = pure ()\n')
            commands=[];stage=types.SimpleNamespace(out=root,work=root,source=root,producer=root,
                auth={'flags':[],'ghc':{'path':'/pinned/ghc'}},manifest={'emlf_modules':[]},
                record={'input_pins':{}},command=lambda label,argv,**kw:commands.append((label,argv)),output_pin=lambda p:None)
            flags=['-prof','-hidir',str(root/'build/objects'),'-odir',str(root/'build/objects')]
            import controller
            with patch.object(controller,'profile_flags',return_value=flags),patch.object(controller,'main_profile_flags',wraps=controller.main_profile_flags) as helper:
                controls.compile_fixture(stage,'fixture',source)
            helper.assert_called_once_with(flags,root/'build/objects',root/'fixture')
            argv=commands[0][1];self.assertEqual(argv[argv.index('-hidir')+1],str(root/'build/objects'))
            self.assertEqual(argv[argv.index('-ohi')+1],str(root/'fixture/Main.p_hi'))
            self.assertEqual(argv[-2:],['-o',root/'fixture/Main.p_o'])
    def test_fixture_link_uses_base_profile_flags_not_one_shot_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'Fixture.hs';source.write_text('module Main where\nmain = pure ()\n')
            commands=[];objects=root/'build/objects';folder=root/'fixture'
            flags=['-prof','-osuf','p_o','-hisuf','p_hi','-O2','-fpedantic-bottoms','-fno-state-hack','-package','base','-hidir',str(objects),'-odir',str(objects)]
            stage=types.SimpleNamespace(out=root,work=root,source=root,producer=root,
                auth={'flags':[],'ghc':{'path':'/pinned/ghc'}},manifest={'emlf_modules':['MLF.Entry.Emlf']},
                record={'input_pins':{}},command=lambda label,argv,**kw:commands.append((label,argv,kw)),output_pin=lambda p:None)
            import controller
            original=list(flags)
            with patch.object(controller,'profile_flags',return_value=flags):controls.compile_fixture(stage,'fixture',source)
            self.assertEqual(flags,original)
            expected_compile=list(original);expected_compile[expected_compile.index('-odir')+1]=str(folder)
            expected_compile += ['-i'+str(objects),'-ohi',str(folder/'Main.p_hi')]
            self.assertEqual(commands[0][1],['/pinned/ghc','-c','-fforce-recomp',*expected_compile,source,'-o',folder/'Main.p_o'])
            self.assertEqual(commands[1][1],['/pinned/ghc',*original,'-rtsopts=ignoreAll','-with-rtsopts=-pj -po'+str(folder/'active')+' -s'+str(folder/'active.stats'),folder/'Main.p_o',objects/'MLF/Entry/Emlf.p_o',root/'build/host.o',root/'build/supervisor.o','-o',folder/'program'])
            for bad in ['-ohi','-c','-fforce-recomp']:self.assertNotIn(bad,commands[1][1])
            self.assertTrue(all(row[2]['maximum']==120 for row in commands))
    def ready_row(self):
        return dict(pid=202,start='22',parent_pid=101,parent_start='11',session=202,parent_session=101)
    def ready_table(self):
        return {202:dict(start='22',ppid=101,state='S'),101:dict(start='11',ppid=404,state='S'),404:dict(start='44',ppid=303,state='S'),303:dict(start='33',ppid=1,state='S')}
    def ready_scope(self):
        return dict(stage_pid=303,stage_start='33',config=Path('/work/run/guard-config.json'),command=['/python','child'],source='/source',output='/work/run',work='/work')
    def ready_load(self,path):
        if str(path)=='/marker':return self.ready_row()
        scope=self.ready_scope();return {k:scope[v] for k,v in [('command','command'),('cwd','source'),('output','output'),('bounded_root','work')]}
    def ready_argv(self,path):
        if str(path)=='/proc/404/cmdline':return ('\0'.join([sys.executable,'-B','/python','/work/run/guard-config.json'])+'\0').encode()
        return b'/python\0child\0'
    def test_readiness_checks_live_identities_sessions_and_executable(self):
        row=self.ready_row();table=self.ready_table()
        with patch.object(controls.O,'load',side_effect=self.ready_load),patch.object(controls.guard,'process_table',return_value=table),patch.object(controls.Path,'resolve',return_value=Path('/python')),patch.object(controls.Path,'read_bytes',autospec=True,side_effect=self.ready_argv),patch.object(controls.os,'getpid',return_value=303),patch.object(controls.os,'getsid',side_effect=lambda pid:pid):
            result=controls.observe_session_ready(Path('/marker'),self.ready_scope())
        self.assertTrue(all(result[k]==v for k,v in row.items()));self.assertEqual(result['supervisor_pid'],404);self.assertEqual(result['stage_pid'],303)
    def test_readiness_spoof_stale_and_identity_race_rejected(self):
        table=self.ready_table()
        for kind in ['wrong-parent','stale-start','same-session','executable','late-race','wrong-guard-argv','late-supervisor-race']:
            first={k:dict(v) for k,v in table.items()};second={k:dict(v) for k,v in table.items()}
            if kind=='wrong-parent':first[202]['ppid']=999
            if kind=='stale-start':first[202]['start']='old'
            if kind=='late-race':second[202]['start']='reused'
            if kind=='late-supervisor-race':second[404]['start']='reused'
            sid=(lambda pid:101) if kind=='same-session' else (lambda pid:pid)
            resolved=[Path('/foreign'),Path('/python')] if kind=='executable' else None
            argv=(lambda path:b'unrelated\0') if kind=='wrong-guard-argv' else self.ready_argv
            with self.subTest(kind=kind),patch.object(controls.O,'load',side_effect=self.ready_load),patch.object(controls.guard,'process_table',side_effect=[first,second]),patch.object(controls.Path,'resolve',side_effect=resolved,return_value=Path('/python')),patch.object(controls.Path,'read_bytes',autospec=True,side_effect=argv),patch.object(controls.os,'getpid',return_value=303),patch.object(controls.os,'getsid',side_effect=sid),self.assertRaises(ValueError):
                controls.observe_session_ready(Path('/marker'),self.ready_scope())
    def test_unrelated_valid_python_pair_rejected_before_arming(self):
        table=self.ready_table();table[404]['ppid']=999
        with patch.object(controls.O,'load',side_effect=self.ready_load),patch.object(controls.guard,'process_table',return_value=table),patch.object(controls.Path,'resolve',return_value=Path('/python')),patch.object(controls.os,'getpid',return_value=303),patch.object(controls.os,'getsid',side_effect=lambda pid:pid),self.assertRaisesRegex(ValueError,'another invocation'):
            controls.observe_session_ready(Path('/marker'),self.ready_scope())
    def test_cancellation_waits_through_slow_precheck_until_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);observed=self.ready_row();record={};stage=types.SimpleNamespace(out=root,source=root,work=root,record=record,output_pin=lambda p:None)
            def guarded(stage,label,argv,reports=(),maximum=15,cancel=None,before_child=None):
                # Longer than the old premature 0.3s timer, simulating recheck.
                time.sleep(.4);self.assertFalse(cancel.is_set());before_child(root/'session-run')
                (root/'cross-session-ready.json').write_text(json.dumps(observed));ready_at=time.monotonic()
                self.assertTrue(cancel.wait(1));self.assertGreaterEqual(time.monotonic()-ready_at,.25)
                return None,dict(reason='cancelled',tracked_processes={'101':'11','202':'22'})
            with patch.object(controls,'observe_session_ready',return_value=observed),patch.object(controls,'guarded',side_effect=guarded):controls.child_session_control(stage)
            self.assertTrue(record['cross_session_readiness']['delay_begins_after_verified_readiness'])
    def test_missing_readiness_is_bounded_and_never_success(self):
        with tempfile.TemporaryDirectory() as d:
            cancel=threading.Event();stop=threading.Event();observed={}
            controls.wait_session_ready(Path(d)/'missing',cancel,stop,observed,{},timeout=.02)
            self.assertTrue(cancel.is_set());self.assertIn('timeout',observed['error']);self.assertNotIn('pid',observed)
    def test_stale_marker_prevents_control_launch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'cross-session-ready.json').write_text('{}');stage=types.SimpleNamespace(out=root)
            with patch.object(controls,'guarded') as run,self.assertRaises(ValueError):controls.child_session_control(stage)
            run.assert_not_called()
    def test_changed_guard_tracking_identity_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);observed=self.ready_row();stage=types.SimpleNamespace(out=root,source=root,work=root,record={},output_pin=lambda p:None)
            def guarded(stage,label,argv,reports=(),maximum=15,cancel=None,before_child=None):
                before_child(root/'session-run')
                (root/'cross-session-ready.json').write_text(json.dumps(observed));self.assertTrue(cancel.wait(1))
                return None,dict(reason='cancelled',tracked_processes={'101':'11','202':'different'})
            with patch.object(controls,'observe_session_ready',return_value=observed),patch.object(controls,'guarded',side_effect=guarded),self.assertRaisesRegex(ValueError,'cancellation not proved'):
                controls.child_session_control(stage)
    def test_real_guarded_hook_runs_after_precheck(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);events=[]
            stage=types.SimpleNamespace(out=root,work=root,source=root,counter=0,start=time.monotonic(),record={'commands':[]},recheck=lambda:events.append('recheck'),save=lambda:None,output_pin=lambda p:None)
            row=dict(cleanup=True,test_only=False,standalone_admission=False,archived={})
            def run(*args,**kwargs):events.append('child');return row
            with patch.object(controls.guard,'run_child',side_effect=run):controls.guarded(stage,'hook',['/python'],before_child=lambda folder:events.append('hook'))
            self.assertEqual(events,['recheck','hook','child','recheck'])
    def test_actual_python_cross_session_readiness_and_cleanup(self):
        # Real lightweight Python children, isolated temporary test locks only.
        from test_guard import GuardTests
        owner=GuardTests();owner.setUp();self.addCleanup(owner.doCleanups)
        root=owner.root;record={};stage=types.SimpleNamespace(out=root,work=root,source=root,record=record,output_pin=lambda p:None)
        def guarded(stage,label,argv,reports=(),maximum=15,cancel=None,before_child=None):
            time.sleep(.35);self.assertFalse(cancel.is_set());before_child(root/'session-run')
            row=controls.guard.run_guard(list(map(str,argv)),cwd=root,output=root/'session-run',locks=owner.locks,epoch=owner.epoch,seconds=3,test_mode=True,cancel_event=cancel,bounded_root=root)
            self.assertTrue(row['cleanup']);self.assertTrue(row['lock_reacquired']);self.assertTrue(row['lease_cleared'])
            return root/'session-run',row
        with patch.object(controls,'guarded',side_effect=guarded):controls.child_session_control(stage)
        observed=record['cross_session_readiness']['observed'];self.assertNotEqual(observed['session'],observed['parent_session'])
    def test_controls_total_uses_single_budget_source(self):
        import controller
        self.assertEqual(controller.BUDGETS['PROBE-CONTROLS'],420)
        self.assertEqual(controls.FIXTURE_COMPILE_LINK_SECONDS,120)
        self.assertIn("BUDGETS['PROBE-CONTROLS']",__import__('inspect').getsource(controls.guarded))
    def test_delayed_producer_positive(self):
        self.assertEqual(controls.positive_producer({'stacks':[row('TOY_PRODUCER',24)]}),24)
    def test_delayed_only_consumer_rejected(self):
        with self.assertRaises(ValueError):controls.positive_producer({'stacks':[row('TOY_CONSUMER',24)]})
    def test_eager_consumer_context_rejected(self):
        with self.assertRaises(ValueError):controls.positive_producer({'stacks':[row('TOY_PRODUCER',24,['TOY_CONSUMER'])]})
    def test_allocation_unit_delta(self):
        a={'stacks':[row('UNIT_ALLOCATION',1048600),row('OTHER',99)]}
        b={'stacks':[row('UNIT_ALLOCATION',1114136),row('OTHER',123456)]}
        self.assertEqual(controls.unit_delta(a,b),65536)
    def test_word_unit_or_missing_tag_rejected(self):
        for delta in (8192,0,-65536):
            with self.subTest(delta=delta),self.assertRaises(ValueError):controls.unit_delta({'stacks':[row('UNIT_ALLOCATION',100000)]},{'stacks':[row('UNIT_ALLOCATION',100000+delta)]})
    def test_actual_posix_owner(self):
        import os
        st=types.SimpleNamespace(st_dev=os.makedev(8,1),st_ino=123)
        self.assertEqual(controls.lock_owner('1: POSIX ADVISORY WRITE 321 08:01:123 0 EOF',st),321)
        for text in ['1: FLOCK ADVISORY WRITE 321 08:01:123 0 EOF','1: POSIX ADVISORY READ 321 08:01:123 0 EOF','1: POSIX ADVISORY WRITE 321 08:01:124 0 EOF','1: POSIX ADVISORY WRITE 321 08:02:123 0 EOF','1: -> POSIX ADVISORY WRITE 321 08:01:123 0 EOF']:
            self.assertIsNone(controls.lock_owner(text,st))
if __name__=='__main__':unittest.main()
