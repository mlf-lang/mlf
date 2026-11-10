#!/usr/bin/env python3
"""Foundation14 only: SETUP fresh builtin+relink120; separately admitted QD420."""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import stat
import sys
import time
import types

HERE = Path(__file__).resolve().parent
HELPER = '0d11b29419a32fc9832096951aa085cc317c8a304b9db110ee96ba411a4ce7cc'
SCOPE = 'd8ffe4256f333c0b48b22b9e68d9c3fa5dc9b471fd22a0d636ba9b157fe419a3'
WATCHDOG = '5368803eb84dabc9dcefa89225b6ff56afd637e105f227bade15e40f9a5e923f'
RUNTIME = '6cfa19c71442422d0a5f1b5386618e60bca6883821ab556a4dff67f3643e7093'
ORACLES = '363067f5d136250bd382d9bfd77234882123e22acc2d8482dedcdc0aafcfd68e'
LIMITS = dict(address_space_per_process_bytes=6*1024**3, disk_free_floor_bytes=5*1024**3,
              host_available_floor_bytes=3*1024**3, max_work_bytes=4*1024**3,
              process_tree_rss_bytes=5*1024**3)
TOOLCHAIN_ALIASES = {
    'ghc':('ghc/bin/ghc','ghc/bin/ghc-9.14.1'),
    'ghc-pkg':('ghc/bin/ghc-pkg','ghc/bin/ghc-pkg-9.14.1'),
    'clang':('bin/clang','debian/usr/lib/llvm-19/bin/clang'),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def exact_module(path, digest, name):
    require(sha(path) == digest, 'reviewed source changed: '+str(path))
    result = types.ModuleType(name); result.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), result.__dict__)
    return result


def toolchain_alias(name,item,root,expected=None):
    """Only three declared official-tool aliases; never a generic pin fallback."""
    require(name in TOOLCHAIN_ALIASES,'unknown toolchain alias')
    require(root.is_absolute() and root.resolve(strict=True)==root,'canonical toolchain root')
    relative,target=TOOLCHAIN_ALIASES[name]
    path=root/relative;resolved=root/target
    require(item.get('path')==str(path) and item.get('resolved_path')==str(resolved),'recorded toolchain alias/resolved path')
    require(path.is_symlink(),'declared toolchain alias must be a symlink')
    binding=os.readlink(path)
    def trace():
        pending=list(path.parts[1:]);current=Path('/');links=[]
        while pending:
            component=pending.pop(0)
            if component in ['', '.']:continue
            if component=='..':current=current.parent;continue
            candidate=current/component;info=candidate.lstat()
            if stat.S_ISLNK(info.st_mode):
                target=os.readlink(candidate);links.append(dict(path=str(candidate),symlink_target=target))
                require(len(links)<=32,'toolchain alias resolution cycle/depth')
                parts=Path(target).parts
                if Path(target).is_absolute():current=Path('/');parts=parts[1:]
                pending=list(parts)+pending
            else:current=candidate
        return current,links
    actual,chain=trace()
    require(actual==resolved and path.resolve(strict=True)==resolved and resolved.resolve(strict=True)==resolved and
            resolved.is_file() and not resolved.is_symlink(),'toolchain alias regular target binding')
    digest=sha(resolved);require(digest==item['sha256'],'toolchain alias resolved SHA')
    result=dict(path=str(path),resolved_path=str(resolved),sha256=digest,symlink_target=binding,symlink_chain=chain)
    require(os.readlink(path)==binding and trace()==(actual,chain) and path.resolve(strict=True)==resolved,
            'toolchain alias changed during authentication')
    require(expected is None or result==expected,'exact admitted toolchain symlink binding changed')
    return result


def parse_statistics(raw):
    """Strict ordinary -s summary; preserve original report separately."""
    text = raw.decode('utf-8')
    def single(pattern):
        rows = re.findall(pattern, text, re.M)
        require(len(rows) == 1, 'missing/duplicate RTS summary field: '+pattern)
        return rows[0]
    def integer(value):
        require(re.fullmatch(r'[0-9][0-9,]*', value), 'RTS integer')
        return int(value.replace(',', ''))
    def finite(value):
        number = float(value)
        require(math.isfinite(number) and number >= 0, 'finite nonnegative RTS value')
        return number
    result = {}
    for key, label in [('allocated_bytes','bytes allocated in the heap'),
                       ('copied_bytes','bytes copied during GC'),('maximum_slop_bytes','bytes maximum slop')]:
        result[key] = integer(single(r'^\s*([\d,]+) '+label+r'\s*$'))
    residency, samples = single(r'^\s*([\d,]+) bytes maximum residency \(([\d,]+) sample\(s\)\)\s*$')
    result.update(maximum_residency_bytes=integer(residency), major_gc_residency_samples=integer(samples))
    memory, unit = single(r'^\s*([\d.]+)\s+([MKG])i?B total memory in use.*$')
    result['rts_memory_in_use'] = dict(value=finite(memory), unit=unit+'B', raw_line=single(r'^(.*total memory in use.*)$'))
    result['times'] = {}
    for label in ['INIT','MUT','GC','EXIT','Total']:
        cpu, elapsed = single(r'^\s*'+label+r'\s+time\s+([\d.]+)s\s+\(\s*([\d.]+)s elapsed\)\s*$')
        result['times'][label] = dict(cpu_seconds=finite(cpu), elapsed_seconds=finite(elapsed))
    result['generations'] = []
    for generation, collections, parallel, cpu, elapsed, average, maximum in re.findall(
            r'^\s*Gen\s+(\d+)\s+([\d,]+) colls,\s+([\d,]+) par\s+([\d.]+)s\s+([\d.]+)s\s+([\d.]+)s\s+([\d.]+)s\s*$', text, re.M):
        result['generations'].append(dict(generation=int(generation), collections=integer(collections),
            parallel_collections=integer(parallel), cpu_seconds=finite(cpu), elapsed_seconds=finite(elapsed),
            average_pause_seconds=finite(average), maximum_pause_seconds=finite(maximum)))
    require([r['generation'] for r in result['generations']] == [0,1], 'ordinary two-generation summary required')
    require(all(r['parallel_collections'] == 0 for r in result['generations']), 'unexpected parallel GC')
    cpu, elapsed = single(r'^\s*Productivity\s+([\d.]+)% of total user,\s+([\d.]+)% of total elapsed\s*$')
    result['productivity_percent'] = dict(user=finite(cpu), elapsed=finite(elapsed))
    require(all(v <= 100 for v in result['productivity_percent'].values()), 'invalid productivity')
    result['limitations'] = 'One completed managed-heap diagnostic; rounded RTS values; residency is sampled major-GC liveness, not peak RSS; no attribution to C01, individual features, C allocation or full90.'
    return result


def guard_limits(outer,maximum):
    limits=outer['limits']
    require(0 < limits['wall_seconds'] <= maximum and
            limits['address_space_per_process']==6*1024**3 and
            limits['process_tree_rss_bytes']==5*1024**3 and
            limits['host_available_floor']==3*1024**3 and
            limits['disk_free_floor']==5*1024**3 and
            limits['max_output_bytes']==4*1024**3,'unchanged admitted guard limits')


def fresh_report(report,identity,count):
    groups=report['groups']
    require(report['format']==1 and report['crate']==identity,'query identity/format')
    require(report['reused_groups']==0 and report['inferred_groups']==len(groups)==count,'exact fresh count/no reuse')
    require(all(g['cached'] is False for g in groups),'target cache hit')
    require(len({g['id'] for g in groups})==len(groups),'duplicate query identity')


def foundation_fresh(report):
    fresh_report(report,'fresh-split/compiler90/mlf-foundation',475)


def foundation_target(plan):
    require(plan['format']=='baseline-gc-foundation14-static-plan-v1' and plan['target']=='foundation14' and
            plan['target_module_count']==14 and plan['target_source_bytes']==173594 and plan['target_fresh_groups']==475 and
            len(plan['slices'])==1 and plan['slices'][0]['name']=='mlf-foundation' and
            plan['slices'][0]['identity']=='fresh-split/compiler90/mlf-foundation' and
            plan['slices'][0]['expected_fresh']==475 and len(plan['slices'][0]['modules'])==14 and
            len({r['module'] for r in plan['slices'][0]['modules']})==14 and
            sum(r['bytes'] for r in plan['slices'][0]['modules'])==173594 and
            plan['slices'][0]['dependencies']==[] and plan['target_dependency_order']==['builtin'],
            'fixed original foundation14 target')


def fixed_builtin_contract(fixed,workspace,builtin):
    require(fixed['complete'] is True and fixed['identity']=='mlf:builtin-shared-haskell-v1:13' and
            fixed['prefix']==str(builtin) and builtin==workspace/'thin-setup/builtin' and
            fixed['fresh_groups']==1 and fixed['reused_groups']==0 and
            fixed['query_lock_reacquired'] is True and fixed['interface_checked'] is True,'complete new SETUP builtin proof')
    require(fixed['fixture_prefix']==str(workspace/'thin-setup/builtin-work/fixture') and
            fixed['fixture_spec']==str(workspace/'thin-setup/builtin-work/fixture.spec') and
            fixed['fixture']==str(workspace/'thin-setup/builtin-work/Fixture.emlf'),'fixed builtin fixture paths')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=['SETUP','QD'])
    p.add_argument('--handoff', type=Path, required=True)
    p.add_argument('--handoff-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    require(sha(a.handoff) == a.handoff_sha256, 'handoff hash')
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'duplicate handoff key');result[key]=value
        return result
    handoff = json.loads(a.handoff.read_text(),object_pairs_hook=unique)
    require(handoff['format'] == 'baseline-gc-handoff-v1', 'explicit new handoff')
    source = Path(handoff['source']); output = a.output.absolute()
    H = exact_module(source/'tools/performance/a1-private-index/helper.py', HELPER, 'guard')
    require(os.environ.get('MLF_BUILD_SCOPE') == str(os.getpgrp()), 'original watchdog scope required')
    require(all(key not in os.environ for key in ['MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT']), 'query instrumentation must be absent')
    budget = {'SETUP':120,'QD':420}[a.phase]; started = time.monotonic()
    record = dict(format='baseline-gc-foundation14-phase-v1', phase=a.phase, complete=False, commands=[], stages=[],
                  input_pins={}, output_pins={}, budget_seconds=budget, per_target_seconds=180,
                  handoff=dict(path=str(a.handoff),sha256=a.handoff_sha256),
                  target='foundation14',inference11=False,full90=False, performance_sample=False, native_generation=False, fixed_point=False)
    save = lambda:H.save(output/'receipt.json', record)
    save(); pins = record['input_pins']; outputs = record['output_pins']; alias_inputs={}
    def pin(path, digest=None):
        path = H.regular(path); value = H.sha(path)
        require(digest is None or value == digest, 'input pin differs: '+str(path))
        require(str(path) not in pins or pins[str(path)] == value, 'conflicting pin')
        pins[str(path)] = value
        return path
    def pinned_json(item):
        return H.load(pin(item['path'], item['sha256']))
    def nested_pins(value):
        if isinstance(value, dict):
            if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
                pin(value['path'],value['sha256'])
            for child in value.values(): nested_pins(child)
        elif isinstance(value,list):
            for child in value: nested_pins(child)
    def output_pin(path):
        path = H.regular(path); outputs[str(path)] = H.sha(path)
    def check_inputs():
        H.check_pins(pins)
        require(set(alias_inputs)==set(TOOLCHAIN_ALIASES),'all three declared alias bindings required')
        for name,(item,root,expected) in alias_inputs.items():toolchain_alias(name,item,root,expected)
    def stage(label, fn):
        row = dict(label=label, complete=False, begin_seconds=time.monotonic()-started)
        record['stages'].append(row); save()
        result = fn(); row.update(complete=True, end_seconds=time.monotonic()-started); save()
        return result
    try:
        with H.SerialLock(source/'.mlf-build'):
            pin(a.handoff,a.handoff_sha256)
            plan = pinned_json(handoff['plan'])
            P = exact_module(HERE/'prepare_plan.py', handoff['planner_sha256'], 'planner')
            for path,digest in [(source/'tools/performance/process-spawn/with_scope.py',SCOPE),
                                (source/'tools/shared/resource_watchdog.py',WATCHDOG),
                                (HERE/'reference/sample-runtime.py',RUNTIME),
                                (HERE/'reference/inference11.py',ORACLES)]: pin(path,digest)
            for path in [HERE/'run_diagnostic.py',HERE/'run-phase.sh',HERE/'run_envelope.py',HERE/'prepare_plan.py',Path(sys.executable).resolve(),
                         source/'tools/shared/test_direct.py',source/'tools/shared/verify_builtin_prelude.py',
                         source/'tools/shared/verify_prepared_libraries.py',source/'tools/shared/builtin_prelude_identity.py']:
                pin(path)
            require(handoff['controller_sha256'] == pins[str(HERE/'run_diagnostic.py')] and
                    handoff['launcher_sha256'] == pins[str(HERE/'run-phase.sh')] and
                    handoff['envelope_sha256'] == pins[str(HERE/'run_envelope.py')], 'reviewed controller/launcher/envelope hashes')
            require(plan['source_commit'] == P.BASE and plan['source'] == str(source) and 'producer' in plan, 'producer-backed f9 plan required')
            foundation_target(plan)
            pin(HERE/'reference/foundation14-source.json',P.FOUNDATION_ROWS)
            workspace = P.safe_absolute(plan['workspace']); producer = Path(plan['producer'])
            require(output == workspace/('thin-setup' if a.phase=='SETUP' else 'execution'), 'phase output path differs')
            P.safe_absolute(output)
            runtime = exact_module(HERE/'reference/sample-runtime.py',RUNTIME,'runtime')
            O = exact_module(HERE/'reference/inference11.py',ORACLES,'oracles')
            library = Path(handoff['runtime_library_dir'])
            require(library.is_absolute() and library.is_dir(), 'current runtime library directory')
            environment = runtime.target_environment(library); H.env = lambda:dict(environment)
            record['environment'] = environment
            def command(label,argv,maximum=15,timed=False,cwd=source,command_environment=None):
                remaining = budget-(time.monotonic()-started)
                require(remaining > 0, 'phase deadline exhausted')
                row = dict(label=label,complete=False); record['commands'].append(row); save()
                wrapped = [sys.executable,'-B',source/'tools/performance/process-spawn/with_scope.py',*argv]
                selected_environment=command_environment if command_environment is not None else environment
                row['execution_environment']=dict(selected_environment)
                H.env=lambda:dict(selected_environment)
                try:
                    result = H.Runner(output,dict(LIMITS,wall_seconds=min(maximum,remaining))).run(
                        wrapped,cwd,output/'commands'/label,timed=timed)
                finally:
                    H.env=lambda:dict(environment)
                row.update(result); save()
                return row,(output/'commands'/label/'stdout').read_bytes(),(output/'commands'/label/'stderr').read_bytes()
            def provenance():
                auth = H.authenticate(producer,source)
                require(sha(producer/'receipt.json') == plan['producer_receipt_sha256'], 'same complete producer')
                pin(producer/'receipt.json',plan['producer_receipt_sha256'])
                nested_pins(auth)
                for key in ['toolchain','installed_dependencies']:
                    for path,digest in auth[key]['files'].items(): pin(path,digest)
                for name,digest in auth['object_inputs'].items(): pin(producer/name,digest)
                for row in auth['commands']: pin(row['log'],row['log_sha256'])
                for name in ['packages.txt','ghc-info.txt']: pin(producer/name)
                evidence = {name:pinned_json(item) for name,item in handoff['producer_evidence'].items()}
                require(plan['producer_outer']==handoff['producer_evidence']['build_outer'],'same admitted producer outer')
                required = {'build_outer','build_controller','controls_outer','controls_controller','authentication','relink','toolchain_setup'}
                require(set(evidence) == required, 'complete producer recovery evidence')
                require(set(handoff['toolchain_aliases'])==set(TOOLCHAIN_ALIASES),'exact admitted toolchain alias inventory')
                for name,value in evidence.items():
                    require(value.get('complete') is True, 'incomplete producer evidence '+name)
                    if name=='toolchain_setup':
                        # This pinned receipt intentionally records launcher aliases.
                        # Everything outside these exact three entries remains strict.
                        remaining=json.loads(json.dumps(value))
                        root=Path(handoff['producer_evidence']['toolchain_setup']['path']).parent
                        for alias in TOOLCHAIN_ALIASES:
                            item=remaining['tool_identities'].pop(alias)
                            expected=handoff['toolchain_aliases'][alias]
                            actual=toolchain_alias(alias,item,root,expected)
                            pin(actual['resolved_path'],actual['sha256'])
                            alias_inputs[alias]=(item,root,expected)
                        record['toolchain_alias_pins']=handoff['toolchain_aliases']
                        nested_pins(remaining)
                    else:
                        nested_pins(value)
                for prefix in ['build','controls']:
                    outer,ctrl = evidence[prefix+'_outer'],evidence[prefix+'_controller']
                    require(outer['exit_code']==0 and outer['reason'] is None and ctrl['watchdog_exit']==0 and
                            not ctrl['remaining_after_watchdog'] and not ctrl['remaining_after_cleanup'] and
                            ctrl['shared_lock_reacquired'] and ctrl['internal_lock_reacquired'], 'upstream guard/cleanup')
                    require(ctrl['cwd']==str(source) and ctrl['bounded_receipt_sha256']==handoff['producer_evidence'][prefix+'_outer']['sha256'], 'upstream guard binding')
                    require(ctrl['prelaunch_source']==ctrl['final_source'] and ctrl['final_source']['commit']==P.BASE, 'upstream frozen source')
                    require(ctrl['command'][-len(outer['command']):]==outer['command'], 'outer controlled command binding')
                build = evidence['build_outer']['command']
                require(build[1:]==['-B',str(source/'tools/shared/build.py'),'--bootstrap-only','--optimization','2','--build-dir',str(producer)] and
                        Path(build[0]).resolve()==Path(auth['orchestrator']['path']), 'actual original producer build command')
                controls = evidence['authentication']
                require(controls['producer_receipt']['sha256']==plan['producer_receipt_sha256'] and
                        controls['full_object_inputs_verified'] is True and
                        [r['label'] for r in controls['commands']]==['version','identity','semantic-42','unicode-positive','type-rejection'] and
                        all(r['passed'] for r in controls['commands']), 'original independent producer controls')
                relink = evidence['relink']
                require(relink['producer']==str(producer) and relink['source']==str(source) and
                        relink['source_commit']==P.BASE and relink['non_main_count']==94, 'relink provenance')
                require({x['module'] for x in relink['non_main_closure']}==set(plan['emlf_non_main_modules']), 'same emlf closure')
                for item in plan['selected_objects_and_interfaces']: pin(item['path'],item['sha256'])
                reconstructed = json.loads(json.dumps(plan))
                P.authenticate_and_commands(reconstructed,H.load(source/'shared-sources.json'),source,producer,
                    Path(handoff['producer_evidence']['build_outer']['path']),handoff['producer_evidence']['build_outer']['sha256'])
                for field in ['thin_setup_command_recipes','selected_objects_and_interfaces','ordinary_binary','statistics_binary','statistics_path']:
                    require(reconstructed[field]==plan[field], 'fresh producer recipe differs '+field)
                for recipe in plan['thin_setup_command_recipes'][:2]:
                    pin(recipe['byte_equality_required_with'],recipe['current_unlisted_original_sha256'])
                for row in plan['full_source_closure']['modules']: pin(row['source'],row['sha256'])
                for part in plan['slices']: nested_pins(part['package_manifest'])
                return auth
            auth = stage('original-producer-authentication',provenance)
            stage('toolchain-aliases-and-inputs-before',check_inputs)
            ordinary = Path(plan['ordinary_binary']['path']); diagnostic = Path(plan['statistics_binary'])
            stats = Path(plan['statistics_path'])
            programs = {'ordinary':ordinary,'python':Path(sys.executable),
                        **{n:Path('/bin')/n for n in ['mkdir','mv','rm','rmdir']}}
            def runtime_snapshot(label,include_diagnostic):
                selected = dict(programs)
                if include_diagnostic: selected['diagnostic']=diagnostic
                result = dict(configuration=runtime.runtime_configuration(H),
                              directory=dict(path=str(library),realpath=str(library.resolve(strict=True))),programs={})
                for name,path in selected.items():
                    identity=runtime.identity(H,path); loader=runtime.elf_interpreter(H,path); loader_id=runtime.identity(H,loader)
                    _,stdout,stderr=command(label+'-'+name,[loader,'--list',path])
                    require(not stderr and identity==runtime.identity(H,path) and loader_id==runtime.identity(H,loader), 'stable runtime executable')
                    result['programs'][name]=dict(executable=identity,loader=loader_id,libraries=runtime.loader_rows(H,stdout,loader))
                if include_diagnostic:
                    require(result['programs']['ordinary']['libraries']==result['programs']['diagnostic']['libraries'], 'same ordinary RTS libraries')
                return result
            if a.phase == 'SETUP':
                require('setup' not in handoff and 'dependencies' not in handoff, 'setup cannot import a prior setup or run dependencies')
                P.absent(diagnostic); P.absent(stats)
                before=stage('runtime-before',lambda:runtime_snapshot('runtime-before',False))
                record['runtime_before']=before;save()
                setup_tmp=output/'tmp';setup_tmp.mkdir(mode=0o700)
                build_environment={**environment,'TMPDIR':str(setup_tmp)}
                record['setup_build_environment']=build_environment;save()
                # Fresh builtin only, charged to SETUP120. No failed-cohort artifact reuse.
                require(plan['builtin_prefix']==str(output/'builtin'),'new setup-local builtin prefix')
                builtin=Path(plan['builtin_prefix']);builtin_work=output/'builtin-work';builtin_work.mkdir(mode=0o700)
                fixture=builtin_work/'Fixture.emlf';fixture.write_bytes(b'module Fixture where\nvalue = 42\n')
                builtin_queries=builtin_work/'queries';builtin_queries.mkdir(mode=0o700)
                builtin_spec=builtin_work/'fixture.spec';fixture_prefix=builtin_work/'fixture'
                builtin_fields=['MLF-CRATE-1','compiler-shapes/builtin','','false',
                    P.pack([P.pack(['Fixture',str(fixture)])]),'',str(builtin_queries),str(builtin)]
                builtin_spec.write_text(P.pack(builtin_fields))
                require(O.unpack(H,builtin_spec.read_text())==builtin_fields,'exact fresh builtin spec')
                for path in [fixture,builtin_spec]:output_pin(path)
                for prefix in [builtin,fixture_prefix]:
                    for suffix in ['.mlfci','.mlfco','.queries']:P.absent(str(prefix)+suffix)
                check_inputs();require(not any(builtin_queries.iterdir()),'fresh builtin fixture queries')
                builtin_result,builtin_stdout,builtin_stderr=command('compile-fixed-builtin',
                    [ordinary,'--compile-crate',builtin_spec,'-o',fixture_prefix],maximum=120)
                require(not builtin_stdout and not builtin_stderr,'fresh builtin fixture output')
                fresh_report(H.load(str(fixture_prefix)+'.queries'),'compiler-shapes/builtin',1)
                for suffix in ['.mlfci','.mlfco','.queries']:output_pin(str(fixture_prefix)+suffix)
                for suffix in ['.mlfci','.mlfco']:output_pin(str(builtin)+suffix)
                _,shown,errors=command('show-builtin-fixture',[ordinary,'--show-crate',str(fixture_prefix)+'.mlfci'])
                require(not errors,'builtin fixture show-crate stderr')
                O.interface(H,shown.decode(),'compiler-shapes/builtin',['Fixture'],{P.BUILTIN:str(builtin)+'.mlfci'})
                _,shown,errors=command('show-fixed-builtin',[ordinary,'--show-crate',str(builtin)+'.mlfci'])
                require(not errors,'builtin show-crate stderr')
                O.interface(H,shown.decode(),P.BUILTIN,['Prelude','MLF.Primitive'],{})
                builtin_lock=H.regular(builtin_queries/'.lock')
                with builtin_lock.open('r+') as stream:
                    fcntl.lockf(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.lockf(stream,fcntl.LOCK_UN)
                output_pin(builtin_lock);check_inputs();H.check_pins(outputs)
                record['builtin']=dict(complete=True,identity=P.BUILTIN,prefix=str(builtin),
                    fixture_prefix=str(fixture_prefix),fixture_spec=str(builtin_spec),fixture=str(fixture),
                    fresh_groups=1,reused_groups=0,query_lock_reacquired=True,interface_checked=True,
                    compile=builtin_result,files=[dict(path=str(builtin)+suffix,sha256=outputs[str(builtin)+suffix])
                                                for suffix in ['.mlfci','.mlfco']])
                save()
                # Separate authored transport control. Never executes emlf-statistics.
                control=output/'stats-control';control.mkdir(mode=0o700)
                control_objects=control/'objects';control_objects.mkdir(mode=0o700)
                control_source=control/'Main.hs'
                control_source.write_text('module Main where\nimport System.Environment (getArgs)\nmain :: IO ()\nmain = getArgs >>= print\n')
                control_binary=control/'program';control_stats=control/'statistics.txt'
                P.safe_absolute(control_stats);P.absent(control_stats)
                control_flags=P.private_flags(auth['flags'],producer,control_objects)
                command('build-statistics-control',[auth['ghc']['path'],*control_flags,'-rtsopts=ignoreAll',
                    '-with-rtsopts=-s'+str(control_stats),str(control_source),'-o',str(control_binary)],maximum=120,
                    command_environment=build_environment)
                with (control/'used-once.json').open('x') as stream:
                    json.dump(dict(binary_sha256=sha(control_binary),target='authored ignoreAll argument control'),stream)
                P.absent(control_stats)
                _,control_stdout,control_stderr=command('run-statistics-control',[control_binary,'+RTS','-A1m','-RTS'])
                require(control_stdout==b'["+RTS","-A1m","-RTS"]\n' and not control_stderr,'ignoreAll literal arguments control')
                control_stats=H.regular(control_stats)
                record['statistics_transport_control']=dict(complete=True,authored_output=True,one_use=True,
                    binary=str(control_binary),raw_path=str(control_stats),raw_sha256=sha(control_stats),
                    statistics=parse_statistics(control_stats.read_bytes()),actual_emlf_launched=False)
                for path in control.rglob('*'):
                    if path.is_file():output_pin(path)
                save()
                (output/'objects').mkdir(mode=0o700)
                main=output/'Main.hs';shutil.copyfile(plan['main']['path'],main)
                require(sha(main)==plan['main']['sha256'],'original Main copy');output_pin(main)
                for item in plan['selected_objects_and_interfaces']:
                    if item['suffix']!='.hi':continue
                    dest=output/'objects'/(item['module'].replace('.','/')+'.hi');dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(item['path'],dest);require(sha(dest)==item['sha256'],'copied interface');output_pin(dest)
                stage('input-pins-before-setup',check_inputs)
                for recipe in plan['thin_setup_command_recipes']:
                    command(recipe['label'],recipe['argv'],maximum=120,cwd=Path(recipe['cwd']),command_environment=build_environment)
                    if 'byte_equality_required_with' in recipe:
                        require(Path(recipe['argv'][-1]).read_bytes()==Path(recipe['byte_equality_required_with']).read_bytes(),'C reconstruction raw byte equality')
                        output_pin(recipe['argv'][-1])
                for path in [diagnostic,output/'objects/Main.o',output/'objects/Main.hi']:output_pin(path)
                P.absent(stats)
                after=stage('runtime-after',lambda:runtime_snapshot('runtime-after',True))
                stripped=json.loads(json.dumps(after));del stripped['programs']['diagnostic']
                require(before==stripped,'setup runtime drift');record['runtime_after']=after
                record['diagnostic_binary']=dict(path=str(diagnostic),sha256=sha(diagnostic))
                record['statistics_path']=str(stats);record['diagnostic_launched']=False
                P.absent(stats)
            else:
                require('setup' in handoff,'QD requires separate completed new foundation SETUP')
                setup_outer=pinned_json(handoff['setup']['outer']);setup=pinned_json(handoff['setup']['work'])
                setup_envelope=pinned_json(handoff['setup']['envelope'])
                guard_limits(setup_outer,120)
                expected_setup=[sys.executable,'-B',str(source/'tools/performance/process-spawn/with_scope.py'),
                    sys.executable,'-B',str(HERE/'run_diagnostic.py'),'SETUP','--handoff',setup['handoff']['path'],
                    '--handoff-sha256',setup['handoff']['sha256'],'--output',str(workspace/'thin-setup')]
                require(setup_outer['command']==expected_setup and setup_envelope['worker_command']==expected_setup and
                    setup_envelope['complete'] is True and setup_envelope['phase']=='SETUP' and
                    setup_envelope['output']==str(workspace/'thin-setup') and
                    setup_envelope['bounded_receipt_sha256']==handoff['setup']['outer']['sha256'] and
                    setup_envelope['work_receipt_sha256']==handoff['setup']['work']['sha256'] and
                    setup_envelope['internal_lock_reacquired'] and setup_envelope['shared_lock_reacquired'] and
                    not setup_envelope['final_live_descendants'] and not setup_envelope['remaining_after_watchdog'] and
                    not setup_envelope['remaining_after_cleanup'] and setup_envelope['handoff']==setup['handoff'] and
                    setup_envelope['controller_sha256']==sha(HERE/'run_diagnostic.py') and setup_outer['limits']['wall_seconds']==120,
                    'thin setup envelope/command/work binding')
                require(setup_outer['complete'] is True and setup_outer['exit_code']==0 and setup_outer['reason'] is None and
                        setup['complete'] is True and setup['phase']=='SETUP' and setup['format']=='baseline-gc-foundation14-phase-v1' and setup['diagnostic_launched'] is False and
                        setup['statistics_transport_control']['complete'] is True,'successful unspent thin setup')
                require(setup['input_pins'][handoff['plan']['path']]==handoff['plan']['sha256'] and
                        setup['input_pins'][str(HERE/'run_diagnostic.py')]==sha(HERE/'run_diagnostic.py') and
                        setup['environment']==environment and setup['toolchain_alias_pins']==handoff['toolchain_aliases'],
                        'same setup plan/controller/environment/alias bindings')
                H.check_pins(setup['input_pins']);H.check_pins(setup['output_pins']);pins.update(setup['input_pins']);pins.update(setup['output_pins'])
                require('dependencies' not in handoff,'no failed or external dependency cohort may be imported')
                fixed=setup['builtin'];builtin=Path(plan['builtin_prefix'])
                fixed_builtin_contract(fixed,workspace,builtin)
                for suffix in ['.mlfci','.mlfco']:
                    path=str(builtin)+suffix
                    require(path in setup['output_pins'],'new builtin output not bound');pin(path,setup['output_pins'][path])
                fresh_report(H.load(fixed['fixture_prefix']+'.queries'),'compiler-shapes/builtin',1)
                require(Path(fixed['fixture']).read_bytes()==b'module Fixture where\nvalue = 42\n','authored builtin fixture source')
                P.absent(stats)
                before=stage('runtime-before',lambda:runtime_snapshot('runtime-before',True))
                require(before==setup['runtime_after'],'runtime differs from setup');record['runtime_before']=before
                _,shown,errors=command('recheck-fixed-builtin',[ordinary,'--show-crate',str(builtin)+'.mlfci'])
                require(not errors,'fixed builtin diagnostic')
                O.interface(H,shown.decode(),P.BUILTIN,['Prelude','MLF.Primitive'],{})
                references=None;reference_query=None;record['legs']=[]
                for label in ['ordinary-Q','diagnostic-D']:
                    recipe=plan['spec_recipes'][label];folder=Path(recipe['directory']);folder.mkdir(mode=0o700)
                    queries=folder/'queries';queries.mkdir(mode=0o700);spec=Path(recipe['spec']);spec.write_text(recipe['packed'])
                    decoded=O.unpack(H,spec.read_text());decoded[6]=plan['spec_recipes']['ordinary-Q']['fields'][6]
                    require(P.pack(decoded)==plan['spec_recipes']['ordinary-Q']['packed'],'only query directory changed')
                    row=dict(label=label,complete=False,spec_sha256=sha(spec));record['legs'].append(row);save()
                    check_inputs();require(not any(queries.iterdir()),'fresh empty query directory')
                    for suffix in ['.mlfci','.mlfco','.queries']:P.absent(recipe['prefix']+suffix)
                    if label=='diagnostic-D':
                        P.safe_absolute(stats);P.absent(stats)
                        claim=Path(plan['statistics_binary']).parent/'used-once.json'
                        with claim.open('x') as stream:json.dump(dict(binary=setup['diagnostic_binary'],target=recipe,claimed_before_launch=True),stream)
                        output_pin(claim);record['one_use_claim']=str(claim);save()
                        P.absent(stats)
                    result,stdout,stderr=command('compile-'+label,recipe['compile_argv'],maximum=180,timed=True)
                    row['compile']=result;save();require(not stdout and not stderr,'unexpected compiler output')
                    paths=[H.regular(recipe['prefix']+suffix) for suffix in ['.mlfci','.mlfco','.queries']]
                    report=H.load(paths[2]);foundation_fresh(report)
                    if references is None:
                        references=paths;reference_query=report
                    else:
                        require(all(path.read_bytes()==ref.read_bytes() for path,ref in zip(paths,references)),'three raw outputs differ from fresh Q')
                        require(report==reference_query,'complete ordered query JSON differs')
                    _,shown,errors=command('show-'+label,recipe['postcheck_argv'])
                    require(not errors,'ordinary show-crate diagnostic')
                    O.interface(H,shown.decode(),'fresh-split/compiler90/mlf-foundation',
                                [r['module'] for r in plan['slices'][-1]['modules']],recipe['dependency_identities'])
                    lock=H.regular(queries/'.lock')
                    with lock.open('r+') as stream:
                        fcntl.lockf(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.lockf(stream,fcntl.LOCK_UN)
                    require(sha(spec)==row['spec_sha256'],'target spec changed');output_pin(spec)
                    for path in paths:output_pin(path)
                    check_inputs();H.check_pins(outputs)
                    row.update(complete=True,fresh_groups=475,reused_groups=0,query_lock_reacquired=True,interface_checked=True,
                               raw_three_equal_to_new_Q=label=='diagnostic-D');save()
                stats=H.regular(stats);require(stats.stat().st_size>0,'empty RTS report');output_pin(stats)
                record['statistics']=parse_statistics(stats.read_bytes());record['statistics_raw']=dict(path=str(stats),sha256=sha(stats))
                after=stage('runtime-after',lambda:runtime_snapshot('runtime-after',True))
                require(before==after,'runtime drift');record['runtime_after']=after
                require(sha(stats)==record['statistics_raw']['sha256'],'statistics overwritten')
            stage('final-input-pins-and-toolchain-aliases',check_inputs)
            stage('final-output-pins',lambda:H.check_pins(outputs))
            require(time.monotonic()-started < budget,'phase deadline')
            record.update(complete=True,elapsed_seconds=time.monotonic()-started);save()
    except BaseException as error:
        record.update(error=repr(error),elapsed_seconds=time.monotonic()-started);save();raise


if __name__ == '__main__':main()
