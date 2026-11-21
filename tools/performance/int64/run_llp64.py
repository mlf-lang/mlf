#!/usr/bin/env python3
"""Exercise the GMP long-width adapter; this does not simulate Windows OS/ABI."""
from pathlib import Path
import argparse, shlex, shutil, subprocess, sys, types

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'tools/testing'))
from receipt_selection import inventory_json, select

PREFIX = 'llp64-controls/'
WIDTH = 'shared-windows-width-controls'
EQUIVALENCE = 'host-runtime-byte-equivalence'
VARIANTS = [('ordinary', []), ('ubsan', ['-fsanitize=undefined','-fno-sanitize-recover=all'])]
MODES = ('direct', 'curried')
NUMERIC = [f'{label}-{mode}' for label, _ in VARIANTS for mode in MODES]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    listing = '--framework-list' in sys.argv[1:]
    parser.add_argument('--framework-list', action='store_true')
    parser.add_argument('--producer',type=Path,required=not listing)
    parser.add_argument('--producer-source',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=not listing)
    parser.add_argument('--reference-runtime',type=Path)
    parser.add_argument('--clang',default='clang')
    args=parser.parse_args()
    labels = [WIDTH, *NUMERIC, *([EQUIVALENCE] if args.reference_runtime else [])]
    exact = select(PREFIX, labels)
    planned = [exact] if exact is not None else labels
    if args.framework_list:
        print(inventory_json(PREFIX, planned))
        return
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    hp=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    producer=args.producer.resolve();source=args.producer_source.resolve();auth=H.authenticate(producer,source)
    limits=dict(address_space_per_process_bytes=6*1024**3,process_tree_rss_bytes=5*1024**3,
                host_available_floor_bytes=3*1024**3,disk_free_floor_bytes=5*1024**3,max_work_bytes=2*1024**3,wall_seconds=600)
    files=[Path(__file__),hp,HERE/'NativeOracle.hs',HERE/'NativeControls.c',ROOT/'tests/native/numeric_width_contract.h',ROOT/'tests/native/windows_runtime.c',producer/'receipt.json',producer/'bin/emlf',ROOT/'tools/testing/receipt_selection.py']
    pins={str(p):H.sha(p) for p in files};pins.update(H.file_pins(ROOT/'runtime'))
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','bdw-gc','gmp'],text=True))
    libs=shlex.split(subprocess.check_output(['pkg-config','--libs','bdw-gc','gmp'],text=True))
    clang=shutil.which(args.clang);H.require(clang is not None,'Clang exists')
    record={'complete':False,'inputs':pins,'limits':limits,'checks':[],'planned_checks':planned,
            'scope':'force the existing GMP LLP64 adapter on the host; neither Windows OS execution nor a full LLP64 ABI emulator',
            'performance_samples':0}
    def save():H.save(out/'receipt.json',record)
    def run(name,argv):return H.Runner(out,limits).run(argv,ROOT,out/name)
    save()
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            runtime=(ROOT/'runtime/mlf_runtime.c').read_text();needle='#include "mlf_integer64.h"'
            H.require(runtime.count(needle)==1,'one integer-width boundary')
            forced=out/'llp64-runtime.c';forced.write_text(runtime.replace(needle,'#undef LONG_MAX\n#define LONG_MAX 2147483647L\n'+needle))
            # Only the conditional adapter branch is forced; all production
            # runtime statements and the shared Windows numeric controls remain.
            probe=out/'width-probe.c'
            probe.write_text('#include "llp64-runtime.c"\n'
                'static void require(int ok,const char *message) { if(!ok) { fprintf(stderr,"%s\\n",message); exit(90); } }\n'
                'static int eq(MlfValue *s,const char *e) { return s->as.string.length==strlen(e) && !memcmp(s->as.string.bytes,e,strlen(e)); }\n'
                '#include "numeric_width_contract.h"\n'
                'int main(void) { check_numeric_widths(); puts("PASS shared Windows numeric-width controls"); return 0; }\n')
            common=[clang,'-O2','-std=c11','-Wall','-Wextra','-Werror',*flags,'-I'+str(ROOT/'runtime')]
            if WIDTH in planned:
                run('width-build',[*common,'-I'+str(ROOT/'tests/native'),probe,*libs,'-lm','-lpthread','-o',out/'width-probe'])
                run('width-run',[out/'width-probe']);H.require((out/'width-run/stdout').read_bytes()==b'PASS shared Windows numeric-width controls\n' and not (out/'width-run/stderr').read_bytes(),'actual shared width controls')
                record['checks'].append(WIDTH);save()
            if any(label in planned for label in NUMERIC):
                run('oracle-build',[auth['ghc']['path'],'--make','-j1','-O2','-package-env','-',
                    '-odir',out/'oracle-objects','-hidir',out/'oracle-objects',HERE/'NativeOracle.hs','-o',out/'oracle'])
                run('oracle-run',[out/'oracle']);corpus=out/'oracle-run/stdout';rows=corpus.read_bytes().splitlines()
                expected=b''.join(row.rsplit(b'\t',1)[1]+b'\n' for row in rows)
                H.require(len(rows)==219284 and len(set(rows))==219277,'complete independent GHC corpus, including seven overlapping literal-show rows')
                record['numeric_rows']=len(rows);record['distinct_numeric_rows']=len(set(rows))
                (out/'expected').write_bytes(expected)
                for label,extra in VARIANTS:
                    selected_modes = [mode for mode in MODES if f'{label}-{mode}' in planned]
                    if not selected_modes:
                        continue
                    binary=out/label
                    run(label+'-build',[*common,*extra,HERE/'NativeControls.c',forced,*libs,'-lm','-lpthread','-o',binary])
                    for mode in selected_modes:
                        name=label+'-'+mode;run(name,[binary,corpus,mode])
                        H.require((out/name/'stdout').read_bytes()==expected and not (out/name/'stderr').read_bytes(),'LLP64 adapter raw numeric output '+name)
                        record['checks'].append(name);save()
            if EQUIVALENCE in planned:
                reference=args.reference_runtime.resolve();old=(reference/'mlf_integer64.h').read_text();new=(ROOT/'runtime/mlf_integer64.h').read_text()
                H.require(old.replace('static int mlf_z_fits_u64','static inline int mlf_z_fits_u64')==new,'only compatibility-header linkage annotation changed')
                H.require((reference/'mlf_runtime.c').read_bytes()==(ROOT/'runtime/mlf_runtime.c').read_bytes(),'same runtime C body')
                shadow=out/'equivalence';shadow.mkdir();(shadow/'runtime.c').write_text(runtime)
                for label,header in [('old',old),('new',new)]:
                    (shadow/'mlf_integer64.h').write_text(header)
                    run(label+'-preprocess',[*common,'-E','-P',shadow/'runtime.c','-o',out/(label+'.i')])
                    run(label+'-object',[*common,'-c',shadow/'runtime.c','-o',out/(label+'.o')])
                for suffix in ['.i','.o']:H.require((out/('old'+suffix)).read_bytes()==(out/('new'+suffix)).read_bytes(),'host active runtime bytes unchanged '+suffix)
                record['host_runtime_byte_equivalent']=True
                record['checks'].append(EQUIVALENCE)
                pins[str(reference/'mlf_integer64.h')]=H.sha(reference/'mlf_integer64.h')
            H.check_pins(pins);H.require(H.authenticate(producer,source)==auth,'producer unchanged');record['complete']=True
    except BaseException as error:record['error']=repr(error);raise
    finally:save()
    print('PASS selected LLP64 case: '+exact if exact else 'PASS GMP LLP64 adapter and shared Windows width controls')

if __name__=='__main__':main()
