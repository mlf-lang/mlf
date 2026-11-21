#!/usr/bin/env python3
"""Independent numeric qualification; no ordinary performance samples."""
from pathlib import Path
import argparse
import sys
import types
import legacy_programs as legacy

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'tools/testing'))
from receipt_selection import inventory_json, select

PREFIX = 'int64-controls/'
OPTIMIZATIONS = ('O0', 'O2')
VARIANTS = [('ordinary', []), ('ubsan', ['-fsanitize=undefined','-fno-sanitize-recover=all'])]
MODES = ('direct', 'curried')
DEMAND = (8,9,10,11,14,15,16,45,108,109,110,111,112,118,119,120,121,122,123,124,128)
REJECTIONS = [(15,str(-2**63),'-1','integer division overflow'),
    (15,'7','0','integer division by zero'),(16,'-7','0','integer division by zero'),
    *[(p,'1','-1','integer shift overflow') for p in [110,111,112]],
    *[(p,str(2**127),'0','integer division by zero') for p in [121,122]],
    *[(p,s,'0','invalid integer input') for p in [17,126] for s in ['+','-','1x','0x10','1.0',' 1','1 ']]]
REGION = 'independent native numeric region'
HOST_LABELS = [f'{name}-{opt}' for opt in OPTIMIZATIONS for name in ('host','contracts','conversion')]
PROGRAM_LABELS = ('program-interpreter','program-native')
EXISTING_LABELS = ('string-index','ready-total','stack')


def native_labels(flavor):
    return [f'native-{flavor}-{name}' for name in (*MODES,'allocation')] + [
        label for mode in MODES for label in [
            *[f'demand-{flavor}-{mode}-{primitive}' for primitive in DEMAND],
            *[f'rejection-{flavor}-{mode}-{index}' for index in range(len(REJECTIONS))]]]


def control_labels(suite):
    suites = {
        'host': HOST_LABELS,
        'native': [name for flavor, _ in VARIANTS for name in native_labels(flavor)],
        'program': PROGRAM_LABELS,
        'compiler': ('compiler',),
        'existing': EXISTING_LABELS,
    }
    if suite in ('all','legacy'):
        suites['legacy'] = [row['label'] for row in legacy.cases(ROOT)] + [
            REGION, *[row['label'] for row in legacy.minimum_regions(ROOT)]]
    keys = ('host','native','legacy','program','compiler','existing') if suite == 'all' else (suite,)
    return [label for key in keys for label in suites[key]]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    listing = '--framework-list' in sys.argv[1:]
    parser.add_argument('--framework-list', action='store_true')
    parser.add_argument('--producer', type=Path, required=not listing, help='authenticated ordinary --bootstrap-only producer')
    parser.add_argument('--output', type=Path, required=not listing)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--clang', default='/usr/bin/clang')
    parser.add_argument('--gc-prefix', type=Path, required=not listing)
    parser.add_argument('--gmp-prefix', type=Path, required=not listing)
    parser.add_argument('--gc-library',type=Path,help='static GC archive when its libdir is a multiarch directory')
    parser.add_argument('--suite', choices=['all', 'host', 'native', 'compiler', 'existing', 'program', 'legacy'], default='all')
    args = parser.parse_args()
    labels = control_labels(args.suite)
    exact = select(PREFIX, labels)
    planned = [exact] if exact is not None else labels
    if args.framework_list:
        print(inventory_json(PREFIX, planned))
        return
    enabled = set(planned)
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
    selection_source = ROOT/'tools/testing/receipt_selection.py'
    pins[str(selection_source)] = H.sha(selection_source)
    pins.update(H.file_pins(source_root / 'runtime'))
    pins.update(H.file_pins(source_root / 'host/ghc'))
    record = dict(complete=False, purpose='numeric correctness only', performance_samples=0,
                  inputs=pins, producer=auth, host=H.host(), limits=limits, checks=[], planned_checks=planned)
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
                for opt in OPTIMIZATIONS:
                    name='host-'+opt
                    if name in enabled:
                        execute(name, build_haskell(name, HERE/'HostControls.hs', opt), 'PASS')
                    for short,source,count,extras in [
                        ('contracts','ContractProbe.hs',89,[]),
                        ('conversion','NumericProbe.hs',722,[ROOT/'tests/shared-host/NumericOracle.c'])]:
                        name=short+'-'+opt
                        if name not in enabled:
                            continue
                        execute(name,build_haskell(name,ROOT/'tests/shared-host'/source,opt,extras=extras),
                                f'TOTAL {count} FAILED 0')
            if selected('native'):
                if any(f'native-{label}-{mode}' in enabled for label, _ in VARIANTS for mode in MODES):
                    oracle=out/'oracle'
                    run('oracle-build',[ghc,'--make','-j1','-O2','-package-env','-',
                        '-odir',out/'oracle-objects','-hidir',out/'oracle-objects',HERE/'NativeOracle.hs','-o',oracle])
                    run('oracle-run',[oracle])
                    corpus=out/'oracle-run/stdout'
                    rows=corpus.read_bytes().splitlines()
                    expected=b''.join(row.rsplit(b'\t',1)[1]+b'\n' for row in rows)
                    (out/'native-expected').write_bytes(expected)
                    record['native_cases_per_execution']=len(rows)
                for label,flags in VARIANTS:
                    if not enabled.intersection(native_labels(label)):
                        continue
                    binary=out/('native-'+label)
                    run('native-'+label+'-build',[args.clang,'-O2','-std=c11',*flags,
                        '-I'+str(source_root/'runtime'),'-I'+str(args.gc_prefix/'include'),'-I'+str(args.gmp_prefix/'include'),
                        HERE/'NativeControls.c',source_root/'runtime/mlf_runtime.c',gc_library,
                        '-L'+str(args.gmp_prefix/'lib'),'-lgmp','-lm','-lpthread','-o',binary])
                    for mode in MODES:
                        name='native-'+label+'-'+mode
                        if name not in enabled:
                            continue
                        run(name,[binary,corpus,mode])
                        H.require((out/name/'stdout').read_bytes()==expected,'raw oracle bytes: '+name)
                        record['checks'].append(name); save()
                    allocation='native-'+label+'-allocation'
                    if allocation in enabled:
                        run(allocation,[binary,'--unsigned-allocation'])
                        record['checks'].append(allocation); save()
                    for mode in MODES:
                        for primitive in DEMAND:
                            name=f'demand-{label}-{mode}-{primitive}'
                            if name not in enabled:
                                continue
                            run(name,[binary,'--demand' if mode=='direct' else '--demand-curried',str(primitive)],expected_exit=1)
                            error=(out/name/'stderr').read_text()
                            H.require('left' in error and 'right' not in error,'left-before-right: '+name)
                            record['checks'].append(name); save()
                        for index,(primitive,left,right,message) in enumerate(REJECTIONS):
                            name=f'rejection-{label}-{mode}-{index}'
                            if name not in enabled:
                                continue
                            corpus_path=out/(name+'.tsv');corpus_path.write_text(f'{primitive}\t{left}\t{right}\tunused\n')
                            run(name,[binary,corpus_path,mode],expected_exit=1)
                            H.require(message in (out/name/'stderr').read_text(),'rejection: '+name)
                            record['checks'].append(name); save()
            if selected('legacy') and enabled.intersection(control_labels('legacy')):
                fixture=ROOT/'tests/Tests/NumericArrays.emlf';pins[str(fixture)]=H.sha(fixture)
                region = {'label': REGION}
                if REGION in enabled:
                    oracle=build_haskell('region-oracle',HERE/'RegionOracle.hs','O0')
                    run('region-oracle-run',[oracle]);region_expected=(out/'region-oracle-run/stdout').read_bytes()
                    H.require(len(region_expected.splitlines())==217,'independent region output inventory')
                    region.update(source=legacy.region_program(ROOT),expected=region_expected.decode(),failure=False,region=True)
                    record['independent_native_region_outputs']=217
                rows=legacy.cases(ROOT)+[region]+list(legacy.minimum_regions(ROOT))
                runtime=out/'legacy-runtime.o'
                run('legacy-runtime-build',[args.clang,'-O2','-std=c11','-I'+str(source_root/'runtime'),'-I'+str(args.gc_prefix/'include'),'-I'+str(args.gmp_prefix/'include'),'-c',source_root/'runtime/mlf_runtime.c','-o',runtime])
                for index,case in enumerate(rows):
                    if case['label'] not in enabled:
                        continue
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
                if exact is None:
                    record['legacy_literal_cases']=43;record['minimum_native_region_cases']=2
                save()
            if enabled.intersection(PROGRAM_LABELS):
                source=HERE/'end-to-end.emlf'; expected=(HERE/'end-to-end.expected').read_bytes()
                if 'program-interpreter' in enabled:
                    run('program-interpreter',[producer/'bin/emlf','--run',source])
                    H.require((out/'program-interpreter/stdout').read_bytes()==expected,'interpreted numeric fixture')
                    record['checks'].append('program-interpreter');save()
                if 'program-native' in enabled:
                    run('program-emit',[producer/'bin/emlf','--emit-llvm',source])
                    llvm=out/'program.ll';llvm.write_bytes((out/'program-emit/stdout').read_bytes())
                    binary=out/'program-native'
                    run('program-build',[args.clang,'-O2','-I'+str(source_root/'runtime'),
                        '-I'+str(args.gc_prefix/'include'),'-I'+str(args.gmp_prefix/'include'),llvm,
                        source_root/'runtime/mlf_runtime.c',gc_library,
                        '-L'+str(args.gmp_prefix/'lib'),'-lgmp','-lm','-lpthread','-o',binary])
                    run('program-native-run',[binary])
                    H.require((out/'program-native-run/stdout').read_bytes()==expected,'native numeric fixture')
                    record['checks'].append('program-native');save()
            if 'compiler' in enabled:
                execute('compiler',build_haskell('compiler',HERE/'CompilerControls.hs','O0',shared=True),'PASS')
            if selected('existing'):
                for name,script in [('string-index','test_native_string_index.py'),('ready-total','test_ready_total.py')]:
                    if name not in enabled:
                        continue
                    run(name+'-command',[sys.executable,'-B',ROOT/'tools/shared'/script,
                        '--compiler',producer/'bin/emlf','--clang',args.clang,'--gc-prefix',args.gc_prefix,
                        '--output',out/name])
                    H.require(H.load(out/name/'receipt.json')['complete'],name+' complete')
                    record['checks'].append(name);save()
                if 'stack' in enabled:
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
