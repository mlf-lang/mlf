#!/usr/bin/env python3
"""Single-target candidate-selection qualification via the existing managed route.
Not a full original direct.main run or per-vector fresh-process equivalence.
The separate source-basis and outer-stage evidence must also pass.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def raw_module(raw, name, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module

def require_o0(producer):
    require(producer.get("complete") is True
            and producer.get("typecheck_only") is False
            and producer.get("producer_host") == "GHC"
            and producer.get("optimization") == "0",
            "fresh executable-producing GHC O0 authentication required")

def check_inputs(inputs):
    for name, expected in inputs.items():
        path = Path(name)
        require(path.is_file() and digest(path.read_bytes()) == expected,
                "qualification input changed: " + name)

def load_context():
    entry_path = HERE / "test_direct_candidate_successor.py"
    worker_path = HERE / "candidate_batch_worker.py"
    entry_raw, worker_raw = entry_path.read_bytes(), worker_path.read_bytes()
    entry = raw_module(entry_raw, "_candidate_qualification_entry", entry_path)
    worker = raw_module(worker_raw, "_candidate_qualification_worker", worker_path)
    raws, pins = worker.snapshot()
    require(raws["test_direct_candidate_successor.py"] == entry_raw
            and raws["candidate_batch_worker.py"] == worker_raw,
            "loaded successor differs from authenticated snapshot")
    require((entry.WORK, entry.CLEANUP, entry.OUTER, entry.CANCEL_GRACE)
            == (600, 10, 625, 25), "unchanged managed candidate-selection budgets required")
    crc = raw_module(raws["test_direct_crc_successor.py"],
                     "_candidate_qualification_crc", HERE / "test_direct_crc_successor.py")
    direct = raw_module(raws["test_direct.py"], "_candidate_qualification_direct",
                        HERE / "test_direct.py")
    require(direct.ROOT == ROOT and entry.HERE == HERE and worker.HERE == HERE,
            "single unchanged checkout root required")
    contract = raw_module(raws["candidate_batch_contract.py"], "_candidate_qualification_contract", HERE / "candidate_batch_contract.py")
    stdlib = raw_module(raws["default_stdlib.py"], "_candidate_qualification_stdlib", HERE / "default_stdlib.py")
    return entry, worker, crc, direct, pins, contract, stdlib

def run_one(entry, worker, crc, direct, pins, output, record, save,
            build_receipt, clang):
    """Production route; no virtual original-main result is manufactured."""
    composed = entry.compose(direct, crc, worker, pins)
    runner = composed.CommandRunner(direct.ROOT, output, record, save)
    argv = [sys.executable, "-B", str(HERE / "test_candidate_selection.py"),
            "--build-receipt", str(build_receipt), "--clang", str(clang),
            "--output", str(output / "candidate-selection")]
    result = runner.run("candidate-selection", argv, timeout=600)
    require(type(result.returncode) is int and result.returncode == 0,
            "managed candidate-selection invocation did not complete successfully")
    return argv


HOST_BANNERS = (b'PASS candidate selection: 8254 cases and 2 demand checks\n'
                b'PASS candidate IDs: 12369 cases and 5 demand checks\n')

def read_bound(path, parent):
    path=Path(path)
    require(path.is_absolute() and path.resolve(strict=True)==path and path.is_relative_to(parent),
            'resolved artifact inside exact target required')
    require(path.is_file(), 'regular target artifact')
    return path.read_bytes()

def native_vectors():
    # Independent reconstruction of the full frozen inventory, including large
    # native-only cases. This does not execute the selector or original main.
    result=[(n,0,ids) for n in (0,1,2,7) for ids in ([],[-1,n],[0,0,1,n-1])]
    sizes=(63,64,65,127,128,255,256,257,1024)
    result += [(n,7,ids) for n in sizes for ids in ([0,n-1],[-1,n,n+1],list(range(0,n,7)))]
    result += [(4096,7,[0,63,64,65,255,256,4095]),(65536,7,[]),
               (65536,7,[0,65535]),(65536,7,[-(2**63),-1,2**63-1]),(131072,7,[0,131071])]
    result += [(n,7,ids) for n in sizes for ids in (list(range(n)),[-1,*range(n),n,2**63-1])]
    require(len(result)==62, '62 frozen vector inventory')
    return result

def native_expected(n,period,indices):
    selected=set(indices)
    return (''.join('i:n%d;'%(i%period if period else i) for i in range(n) if i in selected)
            +'s:super;g:given;i:n0;i:n0;\n').encode('ascii')

def expected_setup(producer, native, build, target):
    """Exact frozen script specification, bound to real authenticated inputs.

    The host fixture uses its original O2 demand-preserving flags, even when
    linked to the freshly authenticated O0 producer objects.
    """
    require_o0(producer)
    require(type(native)is dict and set(native)=={'clang','runtime_flags','link_args'} and
            type(native['clang'])is str and Path(native['clang']).is_absolute() and
            all(type(native[k])is list and all(type(v)is str for v in native[k])
                for k in ('runtime_flags','link_args')),'actual native configuration shape')
    require(type(producer.get('ghc'))is dict and type(producer['ghc'].get('path'))is str and
            Path(producer['ghc']['path']).is_absolute() and
            type(producer.get('object_inputs'))is dict and bool(producer['object_inputs']),
            'authenticated GHC and producer object inventory')
    for p in producer['object_inputs']:
        require(type(p)is str and not Path(p).is_absolute() and '..' not in Path(p).parts,
                'relative producer object identity')
    flags=['-O2','-fpedantic-bottoms','-fno-state-hack','-dcore-lint',
           '-package-env','-','-clear-package-db','-global-package-db',
           '-no-user-package-db','-hide-all-packages']
    for package in ('base','array','bytestring','text','containers','directory'):
        flags += ['-package',package]
    objects=[str(build/p) for p in sorted(producer['object_inputs']) if p.endswith('.o') and p!='objects/Main.o']
    require(bool(objects),'nonempty actual producer link objects')
    ghc=producer['ghc']['path'];clang=native['clang']
    commands={
        'host-compile':([ghc,'-c',*flags,'-i','-i'+str(build/'objects'),
            str(HERE/'fixtures/CandidateSelectionControls.hs'),'-o',str(target/'Main.o'),
            '-ohi',str(target/'Main.hi')],180),
        'host-link':([ghc,*flags,'-rtsopts=ignoreAll',str(target/'Main.o'),*objects,
            str(build/'host.o'),str(build/'supervisor.o'),'-o',str(target/'host-controls')],180),
        'host-controls':([str(target/'host-controls')],180),
        'emit-native':([str(build/'bin/emlf'),'-i',str(ROOT/'libraries/mlf-foundation'),
            '--emit-llvm-gc',str(target/'CandidateSelection.hs')],240),
        'runtime':([clang,'-O2','-std=c11',*native['runtime_flags'],'-I'+str(ROOT/'runtime'),
            '-c',str(ROOT/'runtime/mlf_runtime.c'),'-o',str(target/'runtime.o')],120)}
    for optimization in ('0','2'):
        commands['native-link-O'+optimization]=([clang,'-O'+optimization,'-Wno-override-module',
            str(target/'program.ll'),str(target/'runtime.o'),*native['link_args'],'-lpthread','-ldl',
            '-o',str(target/('native-O'+optimization))],120)
    return commands

def validate_single_result(record, worker, contract, entry, pins, output, argv, authenticated_producer, native):
    commands=record.get('commands')
    require(type(commands)is list and len(commands)==1, 'exactly one managed candidate command')
    command=commands[0]
    require(command.get('name')=='candidate-selection' and command.get('argv')==argv and
            command.get('state')=='passed' and type(command.get('exit_code'))is int and
            command['exit_code']==0, 'single managed candidate route/status')
    require(not any(k in command for k in ('error','evidence_error','cleanup_unverified','leader_reap_unverified')),
            'managed failure or unverified cleanup')
    producer=record.get('producer',{})
    require(len(argv)==9 and argv[:4]==[sys.executable,'-B',str(HERE/'test_candidate_selection.py'),'--build-receipt']
            and argv[4]==producer.get('path') and argv[5]=='--clang' and
            argv[7:]==['--output',str(output/'candidate-selection')] and
            type(producer.get('sha256'))is str and bool(producer['sha256']) and
            record.get('inputs',{}).get(argv[4])==producer['sha256'],
            'exact original route and authenticated receipt instance')
    require(record.get('successor_pins')==pins and command.get('input_pins')==pins,
            'actual helper pins')
    worker_argv=[sys.executable,'-B',str(HERE/'candidate_batch_worker.py'),*argv[3:]]
    guard_path=output/'candidate-selection-supervisor.json'
    execution=[sys.executable,'-B',str(HERE/'crc_process_supervisor.py'),'--receipt',str(guard_path),
               '--work-seconds','600','--cleanup-seconds','10',*worker_argv]
    require(command.get('execution_argv')==execution, 'exact supervisor execution argv')
    for key,value in [('original_timeout_seconds',600),('work_seconds',600),
                      ('cleanup_seconds',10),('timeout_seconds',625)]:
        require(type(command.get(key))is int and command[key]==value, 'fixed command budget: '+key)
    state_path=output/'candidate-selection-batch-worker.json'
    state_raw=read_bound(state_path,output);state=json.loads(state_raw)
    guard_raw=read_bound(guard_path,output);guard=json.loads(guard_raw)
    require(state==command.get('worker') and guard==command.get('supervisor'), 'actual terminal receipt links')
    for label in ('stdout','stderr'):
        raw=read_bound(output/('candidate-selection.'+label),output)
        require(digest(raw)==command.get(label+'_sha256'), 'managed capture changed: '+label)
        if label=='stderr': managed_stderr=raw
    entry.validate_terminal(command['exit_code'],guard,state,managed_stderr,
        worker_argv=worker_argv,pins=pins,producer_path=argv[4],producer_sha=producer['sha256'],work=600,cleanup=10)
    target=output/'candidate-selection'
    original_path=target/'receipt.json'
    original_raw=read_bound(original_path,target);original=json.loads(original_raw)
    require(original==state.get('original_receipt'), 'original receipt disconnected from worker')
    worker.validate_inventory(original,state['physical_commands'],state['logical_indices'],state['batch_commands'])
    require(state.get('fixture_generation')=='candidate-monomorphic-runtime-loop-v1' and
            state.get('source_basis')==contract.SOURCE_BASIS,'exact fixture generation and source basis')
    require(original.get('fresh_process_equivalence_claimed')is False and
            original.get('execution_policy_is_not_completion_evidence')is True and
            original.get('batch_worker_receipt')==str(state_path),'explicit non-fresh execution policy')
    require(type(state.get('logical_vectors'))is list and len(state['logical_vectors'])==96,'96 real projections')
    actual={}
    for row in state['physical_commands']:
        identity=row['id']
        require(Path(identity).name==identity and type(row.get('argv'))is list and
                row['argv'] and all(type(x)is str for x in row['argv']), 'physical identity/argv')
        captures={}
        for label in ('stdout','stderr'):
            path=target/(identity+'.'+label)
            require(row.get(label+'_path')==str(path),'unique physical capture path')
            raw=read_bound(path,target)
            require(digest(raw)==row.get(label+'_sha256'),'actual physical capture hash')
            captures[label]=raw
        require(captures['stderr']==b'', 'unexpected physical diagnostic')
        name=row['original_name']
        limit=(240 if name=='emit-native' else 180 if name in ('host-compile','host-link','host-controls')
               or name.startswith('batch-compile-') or name.startswith('batch-link-') else 120)
        require(type(row.get('timeout_seconds'))is int and row['timeout_seconds']==limit,
                'unchanged actual command limit')
        actual[name]=(row,captures)
    require(original.get('native_configuration')==native and record.get('native_configuration')==native and
            native.get('clang')==argv[6],'independently acquired native configuration link')
    setup=expected_setup(authenticated_producer,native,Path(argv[4]).parent,target)
    for name,(command_argv,timeout) in setup.items():
        actual_row=actual[name][0]
        require(actual_row['argv']==command_argv and actual_row['timeout_seconds']==timeout,
                'actual setup differs from authenticated producer/configuration: '+name)
    host,capture=actual['host-controls']
    require(host['argv']==[str(target/'host-controls')] and capture['stdout']==HOST_BANNERS,
            'actual full host Classes and seven demand checks')
    vectors=native_vectors()
    for optimization in ('0','2'):
        for selector in ('named','ids'):
            for index,(n,period,ids) in enumerate(vectors):
                row,capture=actual['native-O'+optimization+'-'+selector+'-'+str(index)]
                expected_argv=[str(target/('native-O'+optimization)),selector,
                               *map(str,[n,period,len(ids),*ids])]
                require(row['argv']==expected_argv and capture['stdout']==native_expected(n,period,ids),
                        'native original argv/result mismatch')
    raws,again=worker.snapshot()
    require(again==pins,'qualification source/helper drift')
    script=raws['test_candidate_selection.py']
    classes=raws['../../libraries/mlf-inference/Bootstrap/Classes.hs']
    fixture_raw=read_bound(target/'CandidateSelection.hs',target)
    require(fixture_raw==contract.original_fixture(script,classes),'whole original fixture')
    emitted,capture=actual['emit-native']
    build=Path(argv[4]).parent
    require(emitted['argv']==[str(build/'bin/emlf'),'-i',str(ROOT/'libraries/mlf-foundation'),
                             '--emit-llvm-gc',str(target/'CandidateSelection.hs')] and
            read_bound(target/'program.ll',target)==capture['stdout'],'native emitter argv and bytes')
    generated=state.get('generated_artifacts')
    required_generated={str(target/'CandidateSelection.hs')}
    for direction in ('forward','reverse'):
        required_generated.update(str(target/('batch-'+direction+suffix)) for suffix in ('.hs','.o','.hi',''))
    require(type(generated)is dict and set(generated)==required_generated,'exact generated artifact inventory')
    for path,expected in generated.items():
        require(digest(read_bound(path,target))==expected,'generated artifact changed')
    required_original={str(target/name) for name in
        ('host-controls','CandidateSelection.hs','program.ll','runtime.o','native-O0','native-O2')}
    require(type(original.get('artifacts'))is dict and set(original['artifacts'])==required_original,
            'complete original artifact inventory')
    for path,expected in original['artifacts'].items():
        require(digest(read_bound(path,target))==expected,'original artifact changed')
    def replace_operand(command, old, new):
        require(command.count(str(old))==1, 'unique captured host template operand')
        changed=list(command);changed[changed.index(str(old))]=str(new)
        return changed
    host_compile=actual['host-compile'][0]['argv']
    host_link=actual['host-link'][0]['argv']
    for direction in ('forward','reverse'):
        compile_argv=replace_operand(host_compile,HERE/'fixtures/CandidateSelectionControls.hs',
                                     target/('batch-'+direction+'.hs'))
        compile_argv=replace_operand(compile_argv,target/'Main.o',target/('batch-'+direction+'.o'))
        compile_argv=replace_operand(compile_argv,target/'Main.hi',target/('batch-'+direction+'.hi'))
        link_argv=replace_operand(host_link,target/'Main.o',target/('batch-'+direction+'.o'))
        link_argv=replace_operand(link_argv,target/'host-controls',target/('batch-'+direction))
        require(actual['batch-compile-'+direction][0]['argv']==compile_argv and
                actual['batch-link-'+direction][0]['argv']==link_argv,'exact captured host compile/link derivative')
    rebuilt=[];projections=[]
    for direction in ('forward','reverse'):
        source=target/('batch-'+direction+'.hs')
        raw=read_bound(source,target)
        require(contract.restore(raw,direction,script,classes)==fixture_raw and
                contract.generate(fixture_raw,direction,script,classes)==raw,'whole generated inverse')
        for lane in ('host','interpreter'):
            row,capture=actual['batch-'+lane+'-'+direction]
            expected_argv=([str(target/('batch-'+direction))] if lane=='host' else
                [str(build/'bin/emlf'),'-i',str(ROOT/'libraries/mlf-foundation'),'--run',str(source),'--'])
            require(row['argv']==expected_argv,'actual batch argv')
            p=contract.physical_record(row['id'],lane,direction,row['argv'],
                                      capture['stdout'],capture['stderr'],row['exit_code'])
            rebuilt.append(p)
            for index in contract.FORWARD:
                case=contract.cases()[index]
                original_argv=[str(build/'bin/emlf'),'-i',str(ROOT/'libraries/mlf-foundation'),
                               '--run',str(target/'CandidateSelection.hs'),'--',*case['arguments']]
                projections.append(contract.project(p,capture['stdout'],index,original_argv,case['expected']))
    require(rebuilt==state['batch_commands'] and projections==state['logical_vectors'],
            'actual byte projections differ from worker ledger')
    aggregate=contract.aggregate(rebuilt,projections)
    require(aggregate==state.get('batch_aggregate'),'aggregate receipt mismatch')
    return dict(worker_receipt=str(state_path),worker_receipt_sha256=digest(state_raw),
        original_candidate_receipt=str(original_path),original_candidate_receipt_sha256=digest(original_raw),
        guard_receipt=str(guard_path),guard_receipt_sha256=digest(guard_raw),
        physical_commands=263,batch_executions=4,batch_projections=96,
        original_vector_counts=original['vector_counts'],
        host_named_cases=8254,host_id_cases=12369,host_demand_checks=7,
        actual_capture_reconstruction_complete=True,fresh_process_equivalence_claimed=False)

def qualify(build_receipt, binaries, output, clang_name):
    build_receipt = build_receipt.resolve(strict=True)
    binaries = binaries.resolve(strict=True)
    output = output.absolute()
    require(not os.path.lexists(output), "fresh qualification output required")
    output.mkdir(parents=True, exist_ok=False)
    output = output.resolve(strict=True)
    record = dict(format="MLF-candidate-selection-SINGLE-TARGET-QUALIFICATION-1", complete=False,
                  original_direct_main_executed=False, full_direct_suite_qualified=False,
                  scope="Actual full candidate-selection controls through managed route; batch projections not fresh interpreter vectors",
                  source_basis_requirement="Separate qualification-commit and full production-input comparison must pass",
                  commands=[])
    record_path = output / "qualification.json"
    def save():
        temp = record_path.with_suffix(".tmp")
        temp.write_text(json.dumps(record, indent=2) + "\n")
        temp.replace(record_path)
    save()
    try:
        entry, worker, crc, direct, pins, contract, stdlib = load_context()
        record["successor_pins"] = pins
        initial_receipt = digest(build_receipt.read_bytes())
        clang_found = shutil.which(clang_name)
        require(clang_found is not None, "Clang executable not found")
        clang = Path(clang_found).resolve(strict=True)
        require(clang.is_file() and os.access(clang, os.X_OK),
                "regular executable Clang required")
        inputs = {
            str(build_receipt): initial_receipt,
            str(Path(__file__).resolve()): digest(Path(__file__).read_bytes()),
            str(Path(sys.executable).resolve()): digest(Path(sys.executable).resolve().read_bytes()),
            str(clang): digest(clang.read_bytes()),
        }
        record["inputs"] = inputs
        save()
        producer = direct.authenticate_build(build_receipt, binaries)
        require_o0(producer)
        native=stdlib.configuration(str(clang))
        require(native.get('clang')==str(clang),'native configuration resolved a different compiler')
        record['native_configuration']=native
        for name in native['link_args']:
            path=Path(name)
            if path.is_absolute():
                inputs[str(path)]=digest(path.read_bytes())
        check_inputs(inputs)
        require(worker.snapshot()[1] == pins, "successor changed before run")
        record["producer"] = dict(path=str(build_receipt), sha256=initial_receipt,
                                  host=producer["producer_host"], optimization=producer["optimization"])
        record["authentication_before_passed"] = True
        save()
        argv = run_one(entry, worker, crc, direct, pins, output, record, save,
                       build_receipt, clang)
        record["candidate_inventory"] = validate_single_result(record, worker, contract, entry, pins, output, argv, producer, native)
        after = direct.authenticate_build(build_receipt, binaries)
        require_o0(after)
        require(after == producer, "authenticated producer changed during run")
        check_inputs(inputs)
        require(worker.snapshot()[1] == pins, "successor changed after run")
        record["authentication_after_passed"] = True
        record["complete"] = True
    except BaseException as error:
        record["complete"] = False
        record["failure_scope"] = "Not qualified; after-run authentication is claimed only when authentication_after_passed is true"
        record["error"] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        save()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clang", default="clang")
    args = parser.parse_args()
    qualify(args.build_receipt, args.bin_dir, args.output, args.clang)

if __name__ == "__main__":
    main()
