#!/usr/bin/env python3
"""Independent numeric qualification; no ordinary performance samples."""
from pathlib import Path
import argparse
import json
import sys
import types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True, help='authenticated ordinary --bootstrap-only producer')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--clang', default='/usr/bin/clang')
    parser.add_argument('--gc-prefix', type=Path, required=True)
    parser.add_argument('--gmp-prefix', type=Path, required=True)
    parser.add_argument('--gc-library',type=Path,help='static GC archive when its libdir is a multiarch directory')
    parser.add_argument('--suite', choices=['all', 'host', 'native', 'compiler', 'existing', 'program', 'legacy'], default='all')
    args = parser.parse_args()
    helper = ROOT / 'tools/performance/a1-private-index/helper.py'
    H = types.ModuleType('resource_guard'); H.__file__ = str(helper)
    exec(compile(helper.read_bytes(), str(helper), 'exec'), H.__dict__)
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    producer = args.producer.resolve()
    source_root=args.source.resolve()
    auth = H.authenticate(producer, source_root)
    gc_library=args.gc_library or args.gc_prefix/'lib/libgc.a'
    ghc = auth['ghc']['path']
    limits = dict(address_space_per_process_bytes=6*1024**3, disk_free_floor_bytes=5*1024**3,
                  host_available_floor_bytes=3*1024**3, process_tree_rss_bytes=5*1024**3,
                  max_work_bytes=2*1024**3, wall_seconds=600)
    pins = {str(p): H.sha(p) for p in HERE.iterdir() if p.is_file()}
    pins.update(H.file_pins(source_root / 'runtime'))
    pins.update(H.file_pins(source_root / 'host/ghc'))
    record = dict(complete=False, purpose='numeric correctness only', performance_samples=0,
                  inputs=pins, producer=auth, host=H.host(), limits=limits, checks=[])
    def save(): H.save(out / 'receipt.json', record)
    def selected(name): return args.suite in ['all', name]
    def run(name, argv, expected_exit=0):
        return H.Runner(out, limits).run(argv, ROOT, out / name, timed=False, expected_exit=expected_exit)
    def build_haskell(name, source, opt, shared=False, extras=()):
        work = out / (name + '-objects')
        roots = H.load(source_root / 'shared-sources.json')['source_roots'] if shared else ['host/ghc']
        binary = out / name
        run(name + '-build', [ghc, '--make', '-j1', '-'+opt, '-fpedantic-bottoms', '-fno-state-hack',
            '-package-env', '-', '-i', *['-i'+str(source_root / path) for path in roots],
            '-odir', work, '-hidir', work, source, producer / 'host.o', producer / 'supervisor.o',
            *extras, '-o', binary])
        return binary
    def execute(name, binary, expected=None):
        run(name+'-run', [binary])
        if expected is not None:
            H.require(expected in (out/(name+'-run/stdout')).read_text(), 'expected control inventory: '+name)
        record['checks'].append(name); save()
    save()
    try:
        with H.SerialLock(ROOT / '.mlf-build'):
            if selected('host'):
                for opt in ['O0', 'O2']:
                    name='host-'+opt
                    execute(name, build_haskell(name, HERE/'HostControls.hs', opt), 'PASS')
                    for short,source,count,extras in [
                        ('contracts','ContractProbe.hs',89,[]),
                        ('conversion','NumericProbe.hs',722,[ROOT/'tests/shared-host/NumericOracle.c'])]:
                        name=short+'-'+opt
                        execute(name,build_haskell(name,ROOT/'tests/shared-host'/source,opt,extras=extras),
                                f'TOTAL {count} FAILED 0')
            if selected('native'):
                oracle=out/'oracle'
                run('oracle-build',[ghc,'--make','-j1','-O2','-package-env','-',
                    '-odir',out/'oracle-objects','-hidir',out/'oracle-objects',HERE/'NativeOracle.hs','-o',oracle])
                run('oracle-run',[oracle])
                corpus=out/'oracle-run/stdout'
                rows=corpus.read_bytes().splitlines()
                expected=b''.join(row.rsplit(b'\t',1)[1]+b'\n' for row in rows)
                (out/'native-expected').write_bytes(expected)
                for label,flags in [('ordinary',[]),('ubsan',['-fsanitize=undefined','-fno-sanitize-recover=all'])]:
                    binary=out/('native-'+label)
                    run('native-'+label+'-build',[args.clang,'-O2','-std=c11',*flags,
                        '-I'+str(source_root/'runtime'),'-I'+str(args.gc_prefix/'include'),'-I'+str(args.gmp_prefix/'include'),
                        HERE/'NativeControls.c',source_root/'runtime/mlf_runtime.c',gc_library,
                        '-L'+str(args.gmp_prefix/'lib'),'-lgmp','-lm','-lpthread','-o',binary])
                    for mode in ['direct','curried']:
                        name='native-'+label+'-'+mode
                        run(name,[binary,corpus,mode])
                        H.require((out/name/'stdout').read_bytes()==expected,'raw oracle bytes: '+name)
                        record['checks'].append(name); save()
                    run('native-'+label+'-allocation',[binary,'--unsigned-allocation'])
                    record['checks'].append('native-'+label+'-allocation'); save()
                    for mode in ['direct','curried']:
                        for primitive in [8,9,10,11,14,15,16,45,108,109,110,111,112,118,119,120,121,122,123,124,128]:
                            name=f'demand-{label}-{mode}-{primitive}'
                            run(name,[binary,'--demand' if mode=='direct' else '--demand-curried',str(primitive)],expected_exit=1)
                            error=(out/name/'stderr').read_text()
                            H.require('left' in error and 'right' not in error,'left-before-right: '+name)
                            record['checks'].append(name); save()
                        failures=[(15,str(-2**63),'-1','integer division overflow'),
                            (15,'7','0','integer division by zero'),(16,'-7','0','integer division by zero'),
                            *[(p,'1','-1','integer shift overflow') for p in [110,111,112]],
                            *[(p,str(2**127),'0','integer division by zero') for p in [121,122]],
                            *[(p,s,'0','invalid integer input') for p in [17,126]
                              for s in ['+','-','1x','0x10','1.0',' 1','1 ']]]
                        for index,(primitive,left,right,message) in enumerate(failures):
                            name=f'rejection-{label}-{mode}-{index}'
                            corpus_path=out/(name+'.tsv');corpus_path.write_text(f'{primitive}\t{left}\t{right}\tunused\n')
                            run(name,[binary,corpus_path,mode],expected_exit=1)
                            H.require(message in (out/name/'stderr').read_text(),'rejection: '+name)
                            record['checks'].append(name); save()
                record['native_cases_per_execution']=len(rows)
            if selected('legacy'):
                import legacy_programs as legacy
                fixture=ROOT/'tests/Tests/NumericArrays.emlf';pins[str(fixture)]=H.sha(fixture)
                oracle=build_haskell('region-oracle',HERE/'RegionOracle.hs','O0')
                run('region-oracle-run',[oracle]);region_expected=(out/'region-oracle-run/stdout').read_bytes()
                H.require(len(region_expected.splitlines())==217,'independent region output inventory')
                rows=legacy.cases(ROOT)+[{'label':'independent native numeric region','source':legacy.region_program(ROOT),'expected':region_expected.decode(),'failure':False,'region':True}]+list(legacy.minimum_regions(ROOT))
                runtime=out/'legacy-runtime.o'
                run('legacy-runtime-build',[args.clang,'-O2','-std=c11','-I'+str(source_root/'runtime'),'-I'+str(args.gc_prefix/'include'),'-I'+str(args.gmp_prefix/'include'),'-c',source_root/'runtime/mlf_runtime.c','-o',runtime])
                for index,case in enumerate(rows):
                    label='legacy-%02d'%index;source=out/(label+'.emlf');source.write_text(case['source'])
                    expected_exit=1 if case['failure'] else 0
                    run(label+'-interpret',[producer/'bin/emlf','--run',source],expected_exit=expected_exit)
                    run(label+'-emit',[producer/'bin/emlf','--emit-llvm',source])
                    llvm=out/(label+'.ll');llvm.write_bytes((out/(label+'-emit/stdout')).read_bytes())
                    if case.get('region'):H.require('define private ptr @mlf.numeric.' in llvm.read_text(),'actual native numeric region emitted')
                    binary=out/(label+'-native')
                    run(label+'-build',[args.clang,'-O2','-Wno-override-module',llvm,runtime,gc_library,'-L'+str(args.gmp_prefix/'lib'),'-lgmp','-lm','-lpthread','-o',binary])
                    run(label+'-execute',[binary],expected_exit=expected_exit)
                    for mode in ['interpret','execute']:
                        logs=out/(label+'-'+mode)
                        if case['failure']:
                            H.require((logs/'stdout').read_bytes()==b'before\n' and case['expected'] in (logs/'stderr').read_text(),'legacy first error/output: '+case['label'])
                        else:H.require((logs/'stdout').read_bytes()==case['expected'].encode(),'legacy literal output: '+case['label'])
                    record['checks'].append(case['label']);save()
                record['legacy_literal_cases']=43;record['independent_native_region_outputs']=217;record['minimum_native_region_cases']=2;save()
            if selected('program'):
                source=HERE/'end-to-end.emlf'; expected=(HERE/'end-to-end.expected').read_bytes()
                run('program-interpreter',[producer/'bin/emlf','--run',source])
                H.require((out/'program-interpreter/stdout').read_bytes()==expected,'interpreted numeric fixture')
                run('program-emit',[producer/'bin/emlf','--emit-llvm',source])
                llvm=out/'program.ll';llvm.write_bytes((out/'program-emit/stdout').read_bytes())
                binary=out/'program-native'
                run('program-build',[args.clang,'-O2','-I'+str(source_root/'runtime'),
                    '-I'+str(args.gc_prefix/'include'),'-I'+str(args.gmp_prefix/'include'),llvm,
                    source_root/'runtime/mlf_runtime.c',gc_library,
                    '-L'+str(args.gmp_prefix/'lib'),'-lgmp','-lm','-lpthread','-o',binary])
                run('program-native-run',[binary])
                H.require((out/'program-native-run/stdout').read_bytes()==expected,'native numeric fixture')
                record['checks'].extend(['program-interpreter','program-native']);save()
            if selected('compiler'):
                execute('compiler',build_haskell('compiler',HERE/'CompilerControls.hs','O0',shared=True),'PASS')
            if selected('existing'):
                for name,script in [('string-index','test_native_string_index.py'),('ready-total','test_ready_total.py')]:
                    run(name+'-command',[sys.executable,'-B',ROOT/'tools/shared'/script,
                        '--compiler',producer/'bin/emlf','--clang',args.clang,'--gc-prefix',args.gc_prefix,
                        '--output',out/name])
                    H.require(H.load(out/name/'receipt.json')['complete'],name+' complete')
                    record['checks'].append(name);save()
                execute('stack',build_haskell('stack',ROOT/'tools/shared/fixtures/item4/InterpreterStack.hs','O0',shared=True),'PASS')
            H.check_pins(pins)
            H.require(H.authenticate(producer,args.source.resolve())==auth,'producer/source identity unchanged')
            record['complete']=True
    except BaseException as error:
        record['error']=repr(error)
        raise
    finally:
        save()
    print('PASS numeric qualification:', ', '.join(record['checks']))

if __name__ == '__main__':
    main()
