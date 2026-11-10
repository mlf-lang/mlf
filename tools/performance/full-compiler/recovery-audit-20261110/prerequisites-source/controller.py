#!/usr/bin/env python3
"""One separately admitted baseline-only prerequisite cohort. No retry/resume.

Importing this module performs no I/O or compiler launch. run-phase.py owns locks
and the original cross-session watchdog. This worker uses the original H.Runner
unaltered, except its documented environment hook, and original with_scope exec.
"""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import time
import types

HERE = Path(__file__).resolve().parent
BASE = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
SOURCE = HERE.parent/'compiler-audit-source-20261111'
UPSTREAM = HERE.parent/'compiler-baseline-recovery-20261110'
TOOLCHAIN = HERE.parent/'compiler-toolchain-recovery-20261110'
PLANNER = HERE.parent/'compiler-gc-audit-prep-20261110/prepare_plan.py'
REFERENCE = PLANNER.parent/'reference'
WORKSPACE = HERE.parent/'baseline-gc-new-cohort-01'
HELPER = SOURCE/'tools/performance/a1-private-index/helper.py'
SCOPE = SOURCE/'tools/performance/process-spawn/with_scope.py'
WATCHDOG = SOURCE/'tools/shared/resource_watchdog.py'
RUNTIME = REFERENCE/'sample-runtime.py'
FIXED = {
    str(HELPER): '0d11b29419a32fc9832096951aa085cc317c8a304b9db110ee96ba411a4ce7cc',
    str(SCOPE): 'd8ffe4256f333c0b48b22b9e68d9c3fa5dc9b471fd22a0d636ba9b157fe419a3',
    str(WATCHDOG): '5368803eb84dabc9dcefa89225b6ff56afd637e105f227bade15e40f9a5e923f',
    str(RUNTIME): '6cfa19c71442422d0a5f1b5386618e60bca6883821ab556a4dff67f3643e7093',
    str(HERE/'audit16-source-manifest.json'): '9a695adb2393bf61275754a6abad0c8e66f2f0f99e593535c2eff7b3ef92f6ec',
}
ORDER = ['mlf-foundation', 'mlf-language-core', 'mlf-frontend', 'mlf-xmlf']
COUNTS = {'mlf-foundation': (14,173594,475), 'mlf-language-core': (4,86482,74),
          'mlf-frontend': (11,371912,763), 'mlf-xmlf': (6,86429,173)}
BUILTIN = 'mlf:builtin-shared-haskell-v1:13'
FORBIDDEN = ['MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT']
LIMITS = dict(address_space_per_process_bytes=6*1024**3,
              disk_free_floor_bytes=5*1024**3, host_available_floor_bytes=3*1024**3,
              max_work_bytes=4*1024**3, process_tree_rss_bytes=5*1024**3)
UPSTREAM_PATHS = {
    'producer_receipt': UPSTREAM/'build/producer/receipt.json',
    'build_outer': UPSTREAM/'build/bounded-receipt.json',
    'build_controller': UPSTREAM/'build/controller.json',
    'controls_outer': UPSTREAM/'controls/bounded-receipt.json',
    'controls_controller': UPSTREAM/'controls/controller.json',
    'controls_authentication': UPSTREAM/'controls/authentication.json',
    'preflight': UPSTREAM/'static-preflight.json',
    'toolchain_receipt': TOOLCHAIN/'setup-result.json',
    'toolchain_environment': TOOLCHAIN/'environment.sh',
    'build_driver': UPSTREAM/'guarded_stage.py',
    'controls_driver': UPSTREAM/'qualify_producer.py',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def load(path):
    def unique(pairs):
        answer = {}
        for key,value in pairs:
            require(key not in answer, 'duplicate JSON key: '+key)
            answer[key] = value
        return answer
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def save(path, value):
    path = Path(path)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    temp.replace(path)


def safe(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and
            re.fullmatch(r'/[A-Za-z0-9_./-]+',str(path)), 'safe absolute ASCII path required')
    for part in [path,*path.parents]:
        require(not part.is_symlink(), 'symlink path forbidden: '+str(part))
    require(path.resolve() == path, 'canonical path required')
    return path


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.resolve() == path, 'canonical absolute file required')
    require(not any(p.is_symlink() for p in [path,*path.parents]), 'file symlink component forbidden: '+str(path))
    require(stat.S_ISREG(path.lstat().st_mode), 'regular file required: '+str(path))
    return path


def absent(path):
    try:
        Path(path).lstat()
    except FileNotFoundError:
        return
    raise ValueError('fresh absent path required: '+str(path))


def identified(path):
    path = regular(path)
    return dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size)


def check_pins(pins):
    for path,digest in pins.items():
        require(sha(regular(path)) == digest, 'input changed: '+path)


def module(path, digest, name):
    require(sha(regular(path)) == digest, 'module pin differs: '+str(path))
    answer = types.ModuleType(name); answer.__file__ = str(path)
    exec(compile(Path(path).read_bytes(),str(path),'exec'),answer.__dict__)
    return answer


def pack(values):
    return ''.join(str(len(x))+':'+x for x in values)


def unpack(text):
    answer = []
    while text:
        prefix,sep,rest = text.partition(':')
        require(sep and re.fullmatch(r'0|[1-9][0-9]*',prefix), 'noncanonical length')
        size = int(prefix)
        require(size <= len(rest), 'truncated packed field')
        answer.append(rest[:size]); text = rest[size:]
    return answer


def reject_instrumentation(environment):
    require(not any(k in environment for k in FORBIDDEN), 'inherited query instrumentation, even empty')


def fresh(report, identity, count):
    require(type(report['format']) is int and report['format'] == 1 and report['crate'] == identity,
            'query format/crate differs')
    groups = report['groups']
    require(type(report['inferred_groups']) is int and type(report['reused_groups']) is int and
            report['inferred_groups'] == len(groups) == count and report['reused_groups'] == 0,
            'exact fresh count, zero reused required')
    require(all(g['cached'] is False for g in groups), 'cached group forbidden')
    require(len({g['id'] for g in groups}) == count, 'duplicate query identity')


def interface(text, identity, modules, dependencies):
    # Original independent public show-crate grammar, no private artifact decoder.
    lines = text.splitlines()
    require(lines and lines[0] == 'crate '+identity, 'interface identity differs')
    owners = [line[7:] for line in lines if line.startswith('module ')]
    require(len(owners) == len(modules) and set(owners) == set(modules), 'interface module ownership differs')
    deps = [line[11:].split(' ',1) for line in lines if line.startswith('dependency ')]
    found = [(name,tail.rsplit(' ',1)[0]) for name,tail in deps]
    require(len(found) == len(dependencies) and dict(found) == dependencies, 'interface dependency identities/paths differ')


def remaining(deadline, maximum):
    left = (deadline-time.monotonic_ns())/1e9
    require(left > 0, 'total 300-second deadline exhausted')
    return min(maximum,left)


def code_paths():
    return [HERE/'controller.py',HERE/'run-phase.py',HERE/'test_controller.py',
            HERE/'static-tests.json',PLANNER,*sorted(REFERENCE.glob('*'))]


def validate_admission(path, digest):
    require(sha(regular(path)) == digest, 'admission SHA differs')
    a = load(path)
    require(a['format'] == 'baseline-gc-prerequisite-admission-v1' and a['approved'] is True,
            'separate coordinator admission required')
    require(a['phase'] == 'prerequisites-only' and a['total_seconds'] == 300 and
            a['per_compile_seconds'] == 180, 'only fixed prerequisite scope admitted')
    require(a['workspace'] == str(WORKSPACE) and a['source'] == str(SOURCE) and
            a['producer'] == str(UPSTREAM/'build/producer'), 'fixed new cohort/source/producer required')
    python = Path(a['python'])
    require(str(python) == '/usr/bin/python3' and python.resolve(strict=True) == Path(sys.executable).resolve(), 'admitted original Python differs')
    library = safe(a['runtime_library_dir'])
    require(library == TOOLCHAIN/'debian/usr/lib/x86_64-linux-gnu' and library.is_dir(), 'verified runtime directory required')
    require(set(a['code_pins']) == {str(x) for x in code_paths()}, 'complete code/recipe/test pins required')
    check_pins(a['code_pins']); check_pins(FIXED)
    tests = load(HERE/'static-tests.json')
    require(tests['complete'] is True and tests['compiler_started'] is False and
            tests['source_commit'] == BASE, 'successful static tests required')
    for filename in ['controller.py','run-phase.py','test_controller.py']:
        require(tests['tested_code'][str(HERE/filename)] == a['code_pins'][str(HERE/filename)], 'static tests are stale')
    require(set(a['upstream']) == set(UPSTREAM_PATHS), 'complete current upstream handoff required')
    pins = {str(path):digest,**FIXED,**a['code_pins'],str(python.resolve()):sha(python)}
    for key,expected in UPSTREAM_PATHS.items():
        item = a['upstream'][key]
        require(item['path'] == str(expected), 'upstream path mismatch: '+key)
        require(sha(regular(expected)) == item['sha256'], 'upstream hash mismatch: '+key)
        pins[str(expected)] = item['sha256']
    p = a['plan']; require(sha(regular(p['path'])) == p['sha256'], 'final exact plan differs')
    pins[p['path']] = p['sha256']
    plan = load(p['path'])
    require(plan['source_commit'] == BASE and plan['source'] == str(SOURCE) and plan['workspace'] == str(WORKSPACE), 'plan cohort mismatch')
    require(plan['producer'] == a['producer'] and plan['producer_receipt_sha256'] == a['upstream']['producer_receipt']['sha256'], 'plan producer mismatch')
    require(plan['producer_outer'] == a['upstream']['build_outer'], 'plan must bind same successful build guard')
    require(plan['dependency_build_order'] == ORDER, 'only original four dependencies')
    return a,plan,pins


def expected_guard_command(python, stage):
    out = UPSTREAM/stage
    child = ([python,'-B',str(SOURCE/'tools/shared/build.py'),'--bootstrap-only','--optimization','2',
              '--build-dir',str(UPSTREAM/'build/producer')] if stage == 'build' else
             [python,'-B',str(UPSTREAM/'qualify_producer.py')])
    return [python,'-B',str(WATCHDOG),'--seconds','600' if stage == 'build' else '120',
            '--address-space-mib','6144','--rss-mib','5120','--max-output-mib','2048',
            '--disk-free-mib','5120',str(out),*child],child


def bind_upstream(a, auth):
    for stage in ['build','controls']:
        ctrl = load(a['upstream'][stage+'_controller']['path'])
        guard = load(a['upstream'][stage+'_outer']['path'])
        expected,child = expected_guard_command(a['python'],stage)
        require(ctrl['complete'] is True and ctrl['stage'] == stage and ctrl['watchdog_exit'] == 0 and
                ctrl['cwd'] == str(SOURCE) and ctrl['command'] == expected, 'bound successful '+stage+' command/cwd required')
        require(ctrl['bounded_receipt_sha256'] == a['upstream'][stage+'_outer']['sha256'] and
                ctrl['controller_sha256'] == a['upstream']['build_driver']['sha256'] and
                ctrl['setup_result_sha256'] == a['upstream']['toolchain_receipt']['sha256'] and
                ctrl['toolchain_environment_sha256'] == a['upstream']['toolchain_environment']['sha256'], 'bound envelope/toolchain differs')
        require(ctrl['shared_lock_reacquired'] is True and ctrl['internal_lock_reacquired'] is True and
                not ctrl['remaining_after_watchdog'] and not ctrl['remaining_after_cleanup'], 'producer cleanup/lock proof required')
        require(guard['complete'] is True and guard['exit_code'] == 0 and guard['reason'] is None and guard['command'] == child,
                'successful exact '+stage+' bounded command required')
        require(guard['limits'] == dict(wall_seconds=600 if stage=='build' else 120,address_space_per_process=6*1024**3,
                process_tree_rss_bytes=5*1024**3,host_available_floor=3*1024**3,disk_free_floor=5*1024**3,
                max_output_bytes=2*1024**3), 'original upstream guard limits differ')
        require(ctrl['environment']['LD_LIBRARY_PATH'] == a['runtime_library_dir'], 'upstream runtime library differs')
        require(ctrl['source']['pin_file_sha256'] == a['upstream']['preflight']['sha256'], 'source preflight differs')
    post = load(a['upstream']['controls_authentication']['path'])
    require(post['complete'] is True and post['no_target_compilation'] is True and post['full_object_inputs_verified'] is True,
            'completed producer postcontrols required')
    require(post['producer_receipt'] == identified(UPSTREAM_PATHS['producer_receipt']) and
            post['driver'] == identified(UPSTREAM_PATHS['controls_driver']) and
            post['object_inputs_count'] == len(auth['object_inputs']) and post['outputs'] == auth['outputs'], 'postcontrols bound to exact producer')
    require([r['label'] for r in post['commands']] == ['version','identity','semantic-42','unicode-positive','type-rejection'], 'full postcontrol inventory required')
    for row,code in zip(post['commands'],[0,0,0,0,1]):
        require(row['passed'] is True and row['exit_code'] == code and row['cwd'] == str(SOURCE) and
                row['argv'][0] == str(UPSTREAM/'build/producer/bin/emlf'), 'failed or unrelated postcontrol')
        for key in ['stdout','stderr']:
            require(identified(row[key]['path']) == row[key], 'postcontrol log changed')
    require(load(a['upstream']['toolchain_receipt']['path'])['complete'] is True, 'toolchain restoration incomplete')


def object_inputs(auth, producer):
    expected = auth['object_inputs']
    require(isinstance(expected,dict) and expected, 'full object_inputs map required')
    files = [p for p in (producer/'objects').rglob('*') if p.is_file() or p.is_symlink()]
    actual = {str(p.relative_to(producer)):sha(regular(p)) for p in files}
    require(actual == expected, 'full object_inputs path/hash inventory differs')
    require(all(k.startswith('objects/') and '..' not in Path(k).parts and not Path(k).is_absolute() for k in expected), 'unsafe object key')
    return {str(producer/k):v for k,v in expected.items()}


def source_inputs(a, plan, planner):
    # Recompute only the static recipe function, not the CLI's absent-root gate.
    expected,_ = planner.source_plan(SOURCE,WORKSPACE)
    for key,value in expected.items():
        if key == 'producer_authentication':
            continue
        if key == 'spec_recipes':
            require(set(plan[key]) == set(value), 'exact recipe names required')
            for name,recipe in value.items():
                for field,item in recipe.items():
                    require(plan[key][name][field] == item, 'source recipe differs: '+name+'/'+field)
            continue
        require(plan.get(key) == value, 'source/static recipe differs: '+key)
    pre = load(UPSTREAM_PATHS['preflight'])
    require(pre['complete'] is True and pre['commit'] == BASE and pre['source'] == str(SOURCE), 'fixed source preflight required')
    pins = {str(SOURCE/k):v for k,v in pre['tracked_files_sha256'].items()}
    for key in pre['tracked_files_sha256']:
        require(not Path(key).is_absolute() and '..' not in Path(key).parts, 'unsafe source pin')
    audit = load(HERE/'audit16-source-manifest.json')
    require(audit['source_commit'] == BASE and len(audit['source_files']) == 16, 'original audit16 required')
    for row in audit['source_files']:
        path = SOURCE/row['path']
        require(pins[str(path)] == row['sha256'] and path.stat().st_size == row['bytes'], 'original audit16 differs')
    check_pins(pins)
    return pins


def builtin_recipe():
    directory = WORKSPACE/'dependencies/builtin-work'
    fixture = directory/'Fixture.emlf'
    fields = ['MLF-CRATE-1','compiler-shapes/builtin','','false',pack([pack(['Fixture',str(fixture)])]),
              '',str(directory/'queries'),str(WORKSPACE/'dependencies/builtin')]
    return dict(directory=str(directory),spec=str(directory/'fixture.spec'),fields=fields,packed=pack(fields),
                prefix=str(directory/'fixture'),dependency_identities={},fixture=str(fixture))


def validate_recipe(recipe, part, built):
    fields = recipe['fields']
    require(len(fields) == 8 and unpack(recipe['packed']) == fields and pack(fields) == recipe['packed'], 'inverse pack mismatch')
    if part is not None:
        require(part['name'] in ORDER and part['modules'] == sorted(part['modules'],key=lambda r:r['module']), 'fixed sorted dependency ownership required')
        count,size,fresh_count = COUNTS[part['name']]
        require(len(part['modules']) == count and sum(r['bytes'] for r in part['modules']) == size and part['expected_fresh'] == fresh_count, 'slice inventory mismatch')
        require(fields[:4] == ['MLF-CRATE-1',part['identity'],'','false'] and part['identity'] == 'fresh-split/compiler90/'+part['name'], 'original identity/entry/options')
        require(fields[4] == pack([pack([r['module'],r['source']]) for r in part['modules']]), 'source transport order changed')
        require(part['dependencies'] == sorted(part['dependencies']) and all(d in built for d in part['dependencies']), 'dependency order or missing prerequisite')
        paths = [str(WORKSPACE/'dependencies/builtin')+'.mlfci',*[built[d]['prefix']+'.mlfci' for d in part['dependencies']]]
        identities = {BUILTIN:paths[0],**{'fresh-split/compiler90/'+d:built[d]['prefix']+'.mlfci' for d in part['dependencies']}}
        require(fields[5] == pack(paths) and recipe['dependency_identities'] == identities, 'original direct dependencies/paths')
    require(fields[6] == str(Path(recipe['directory'])/'queries') and fields[7] == str(WORKSPACE/'dependencies/builtin'), 'query/builtin recipe differs')
    for key in ['directory','spec','prefix']:
        require(safe(recipe[key]).is_relative_to(WORKSPACE/'dependencies'), 'prerequisite path outside dependencies')


def worker(admission_path, admission_sha, deadline_ns):
    require(os.environ.get('MLF_BUILD_SCOPE') == str(os.getpgrp()), 'original watchdog/with_scope required')
    a,plan,pins = validate_admission(admission_path,admission_sha)
    H = module(HELPER,FIXED[str(HELPER)],'original_guard')
    runtime = module(RUNTIME,FIXED[str(RUNTIME)],'original_runtime')
    planner = module(PLANNER,a['code_pins'][str(PLANNER)],'static_recipe')
    environment = runtime.target_environment(Path(a['runtime_library_dir']))
    reject_instrumentation(os.environ)
    H.env = lambda: dict(environment)
    out = WORKSPACE/'prerequisites'; out.mkdir(mode=0o700)
    record = dict(format='baseline-gc-dependencies-v1',complete=False,phase='prerequisites-only',
                  plan=a['plan'],producer_receipt=a['upstream']['producer_receipt'],new_cohort=True,
                  input_pins=pins,output_pins={},environment=environment,commands=[],stages=[],
                  slices=[],total_budget_seconds=300,per_compile_seconds=180,
                  full90=False,inference_target_started=False,native_generation=False,fixed_point=False,
                  historical_artifacts_available=False,performance_samples=0,deadline_monotonic_ns=deadline_ns)
    write = lambda:save(out/'receipt.json',record)
    write(); outputs = record['output_pins']; producer = Path(a['producer'])

    def stage(label, action):
        remaining(deadline_ns,300)
        row = dict(label=label,complete=False,started_monotonic_ns=time.monotonic_ns())
        record['stages'].append(row); write()
        result = action()
        remaining(deadline_ns,300)
        row.update(complete=True,finished_monotonic_ns=time.monotonic_ns()); write()
        return result

    def command(label, argv, maximum=15, compile_crate=False):
        cap = remaining(deadline_ns,maximum)
        row = dict(label=label,complete=False,compile_crate=compile_crate)
        record['commands'].append(row); write()
        folder = out/'commands'/label
        wrapped = [a['python'],'-B',str(SCOPE),*[str(x) for x in argv]]
        try:
            result = H.Runner(WORKSPACE,dict(LIMITS,wall_seconds=cap)).run(wrapped,SOURCE,folder,timed=compile_crate)
            row.update(result); write()
        finally:
            receipt = folder/'command.json'
            if receipt.is_file():
                row.update(load(receipt)); write()
        remaining(deadline_ns,300)
        return row,(folder/'stdout').read_bytes(),(folder/'stderr').read_bytes()

    def pin_output(path):
        path = regular(path); outputs[str(path)] = sha(path)
        return identified(path)

    def runtime_snapshot(label):
        result = dict(configuration=runtime.runtime_configuration(H),
                      directory=dict(path=a['runtime_library_dir'],realpath=str(Path(a['runtime_library_dir']).resolve(strict=True))),programs={})
        programs = {'ordinary':producer/'bin/emlf','python':Path(a['python']),**{n:Path('/bin/'+n) for n in ['mkdir','mv','rm','rmdir']}}
        for name,path in programs.items():
            ident = runtime.identity(H,path); loader = runtime.elf_interpreter(H,path); loader_ident = runtime.identity(H,loader)
            _,stdout,stderr = command(label+'-'+name,[loader,'--list',path])
            require(not stderr and runtime.identity(H,path) == ident and runtime.identity(H,loader) == loader_ident, 'stable ELF runtime files')
            result['programs'][name] = dict(executable=ident,loader=loader_ident,libraries=runtime.loader_rows(H,stdout,loader))
        return result

    def authenticate():
        verified = H.authenticate(producer,SOURCE)  # Original test_direct.authenticate_build unchanged.
        require(verified['optimization'] == '2' and verified['prepared_verification']['kind'] == 'empty' and
                len(verified['shared_inputs']) == 137 and len(verified['resolved_host_modules']) == 4 and
                len(verified['outputs']) == 13, 'full ordinary bootstrap producer only')
        full_objects = object_inputs(verified,producer)
        bind_upstream(a,verified)
        return verified,full_objects

    def check_outputs():
        check_pins(outputs)

    def compile_one(label,recipe,part,built):
        stage('pre-pins-'+label,lambda:(check_pins(pins),check_outputs()))
        validate_recipe(recipe,part,built)
        folder = safe(recipe['directory']); folder.mkdir(mode=0o700)
        queries = folder/'queries'; queries.mkdir(mode=0o700)
        if part is None:
            Path(recipe['fixture']).write_bytes(b'module Fixture where\nvalue = 42\n')
            pin_output(recipe['fixture'])
        spec = Path(recipe['spec']); spec.write_text(recipe['packed'])
        require(spec.read_bytes() == pack(unpack(spec.read_text())).encode(), 'exact transport roundtrip')
        pin_output(spec)
        prefix = Path(recipe['prefix'])
        require(not any(queries.iterdir()), 'query cache must start empty')
        for suffix in ['.mlfci','.mlfco','.queries']:
            absent(str(prefix)+suffix)
        row = dict(name=label,complete=False,identity=recipe['fields'][1],prefix=str(prefix),spec=identified(spec),
                   queries=str(queries),dependency_identities=recipe['dependency_identities'],files=[])
        if part: row.update(modules=part['modules'],expected_fresh=part['expected_fresh'])
        record['slices'].append(row); write()
        result,stdout,stderr = command('compile-'+label,[producer/'bin/emlf','--compile-crate',spec,'-o',prefix],180,True)
        row['compile'] = result; write()
        require(not stdout and not stderr, 'ordinary compile must have empty stdout/stderr')
        for suffix in ['.mlfci','.mlfco','.queries']:
            row['files'].append(pin_output(str(prefix)+suffix))
        count = part['expected_fresh'] if part else 1
        fresh(load(str(prefix)+'.queries'),row['identity'],count)
        _,shown,errors = command('show-'+label,[producer/'bin/emlf','--show-crate',str(prefix)+'.mlfci'])
        require(not errors, 'ordinary show-crate stderr')
        expected_deps = recipe['dependency_identities'] if part else {BUILTIN:str(WORKSPACE/'dependencies/builtin')+'.mlfci'}
        interface(shown.decode(),row['identity'],[r['module'] for r in part['modules']] if part else ['Fixture'],expected_deps)
        lock = regular(queries/'.lock')
        with lock.open('r+') as stream:
            fcntl.lockf(stream,fcntl.LOCK_EX|fcntl.LOCK_NB); fcntl.lockf(stream,fcntl.LOCK_UN)
        pin_output(lock)
        if part is None:
            builtin = WORKSPACE/'dependencies/builtin'
            row['builtin_files'] = [pin_output(str(builtin)+s) for s in ['.mlfci','.mlfco']]
            _,shown,errors = command('show-builtin',[producer/'bin/emlf','--show-crate',str(builtin)+'.mlfci'])
            require(not errors, 'builtin show-crate stderr')
            interface(shown.decode(),BUILTIN,['Prelude','MLF.Primitive'],{})
            record['builtin'] = dict(identity=BUILTIN,prefix=str(builtin),files=row['builtin_files'],interface_checked=True)
        stage('post-pins-'+label,lambda:(check_pins(pins),check_outputs()))
        row.update(complete=True,fresh_groups=count,reused_groups=0,query_lock_reacquired=True,interface_checked=True)
        write(); return row

    try:
        source_pins = stage('source-inventory-before',lambda:source_inputs(a,plan,planner)); pins.update(source_pins)
        auth,objects = stage('authenticate-producer-before',authenticate); pins.update(objects)
        pins.update({r['path']:r['sha256'] for r in auth['outputs'].values()})
        for key in ['packages.txt','ghc-info.txt']:
            pins[str(producer/key)] = sha(producer/key)
        for cmd in auth['commands']:
            pins[cmd['log']] = cmd['log_sha256']
        for row in load(UPSTREAM_PATHS['controls_authentication'])['c_objects']:
            pins[row['object']['path']] = row['object']['sha256']
        record['source_pins_count'] = len(source_pins); record['object_inputs_count'] = len(objects); write()
        record['runtime_before'] = stage('runtime-before',lambda:runtime_snapshot('runtime-before')); write()
        (WORKSPACE/'dependencies').mkdir(mode=0o700)
        stage('builtin',lambda:compile_one('builtin-fixture',builtin_recipe(),None,{}))
        built = {}
        for name in ORDER:
            part = next(r for r in plan['slices'] if r['name'] == name)
            row = stage(name,lambda name=name,part=part:compile_one(name,plan['spec_recipes'][name],part,built))
            built[name] = row
        record['runtime_after'] = stage('runtime-after',lambda:runtime_snapshot('runtime-after'))
        require(record['runtime_after'] == record['runtime_before'], 'runtime mappings/configuration changed')
        require(stage('authenticate-producer-after',authenticate) == (auth,objects), 'producer changed during prerequisites')
        require(stage('source-inventory-after',lambda:source_inputs(a,plan,planner)) == source_pins, 'source inventory changed')
        stage('all-inputs-after',lambda:check_pins(pins)); stage('all-outputs-after',check_outputs)
        record['dependencies'] = {n:built[n] for n in ORDER}
        # Pin raw query cache files too, retaining them separately from the .queries report.
        record['query_cache_pins'] = {str(regular(p)):sha(p) for row in record['slices']
                                      for p in Path(row['queries']).rglob('*') if p.is_file() or p.is_symlink()}
        outputs.update(record['query_cache_pins']); check_outputs()
        require(not (WORKSPACE/'execution').exists() and not (WORKSPACE/'thin-setup').exists(), 'no target or thin setup allowed')
        remaining(deadline_ns,300)
        record['complete'] = True; write()
    except BaseException as error:
        record['error'] = type(error).__name__+': '+str(error); write(); raise
    finally:
        record['finished_monotonic_ns'] = time.monotonic_ns(); write()
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--admission',type=Path,required=True); p.add_argument('--admission-sha256',required=True)
    p.add_argument('--deadline-monotonic-ns',type=int,required=True)
    a = p.parse_args(); worker(a.admission,a.admission_sha256,a.deadline_monotonic_ns)


if __name__ == '__main__':
    main()
