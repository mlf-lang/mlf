#!/usr/bin/env python3
"""One instrumented current-workload run, never an ordinary timing sample."""
from pathlib import Path
import argparse
import json
import os
import shutil
import types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OWNER = 'libraries/mlf-xmlf/Bootstrap/X/Type.hs'
OWNER_SHA = '5ae7191adc5df556b83901682ee17e3de889a99e9fe35e97d7370ec2443d0d3d'
LIMITS = dict(address_space_per_process_bytes=6*1024**3,
              disk_free_floor_bytes=5*1024**3,
              host_available_floor_bytes=3*1024**3,
              max_work_bytes=4*1024**3,
              process_tree_rss_bytes=5*1024**3,
              wall_seconds=600)


def module(path, name):
    result = types.ModuleType(name)
    result.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), result.__dict__)
    return result


def pack(fields):
    return ''.join(str(len(field))+':'+field for field in fields)


def same_bytes(first, second):
    with first.open('rb') as a, second.open('rb') as b:
        while True:
            x, y = a.read(1024*1024), b.read(1024*1024)
            if x != y:
                return False
            if not x:
                return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--producer-source', type=Path, required=True)
    parser.add_argument('--workload', type=Path, required=True)
    parser.add_argument('--setup', type=Path, required=True)
    parser.add_argument('--reference-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, producer = args.producer_source.resolve(), args.producer.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    helper_path = source/'tools/performance/a1-private-index/helper.py'
    H = module(helper_path, 'guard')
    I = module(HERE/'instrument.py', 'instrument')
    record = dict(complete=False, diagnostic_only=True, performance_samples=0,
                  compiler_speedup_claim=False, limits=LIMITS, commands=[])
    save = lambda: H.save(out/'receipt.json', record)
    save()
    try:
        with H.SerialLock(source/'.mlf-build'):
            authenticated = H.authenticate(producer, source)
            H.require(H.sha(source/OWNER) == OWNER_SHA, 'frozen Type owner changed')
            workload, setup = H.load(args.workload), H.load(args.setup)
            H.require(len(workload['modules']) == workload['module_count'] and
                      set(workload['input_files']) == {row['source'] for row in workload['modules']},
                      'workload inventory is incomplete')
            pins = dict(workload['input_files'])
            for path in [args.workload.resolve(), args.setup.resolve(), helper_path,
                         HERE/'instrument.py', HERE/'Counters.hs', Path(__file__).resolve(),
                         producer/'receipt.json', source/OWNER]:
                pins[str(path)] = H.sha(path)
            reference = args.reference_prefix.resolve()
            for extension in ['.mlfci','.mlfco','.queries']:
                path = Path(str(reference)+extension)
                pins[str(path)] = H.sha(path)
            H.check_pins(pins)
            private = out/'source'
            owner = private/'Bootstrap/X/Type.hs'
            owner.parent.mkdir(parents=True)
            changed, edits = I.instrument((source/OWNER).read_bytes())
            owner.write_text(changed)
            shutil.copy2(HERE/'Counters.hs', private/'KindCounters.hs')
            (private/'Main.hs').write_text('''module Main where
import Control.Exception(finally)
import MLF.Host.IO(runEntry)
import qualified MLF.Entry.Emlf as Entry
import qualified KindCounters
main = runEntry Entry.main `finally` KindCounters.report
''')
            record['transformation'] = dict(owner=OWNER, before=OWNER_SHA,
                                             after=H.sha(owner), reversible=True, edits=edits)
            # The ordinary producer is read-only. GHC sees copied interfaces
            # and invalidates downstream code after the changed Type interface.
            copied = {}
            for relative, digest in authenticated['object_inputs'].items():
                if not relative.startswith('objects/') or not relative.endswith(('.o','.hi')):
                    continue
                original = producer/relative
                H.require(H.sha(original) == digest, 'producer object changed: '+relative)
                target = out/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target)
                H.require(H.sha(target) == digest, 'object copy mismatch: '+relative)
                copied[relative] = digest
            for name in ['Main','Bootstrap/X/Type']:
                for extension in ['.o','.hi']:
                    (out/'objects'/Path(name+extension)).unlink(missing_ok=True)
            flags, skip = [], False
            for flag in authenticated['flags']:
                if skip:
                    skip = False
                    continue
                if flag in ['-odir','-hidir']:
                    skip = True
                else:
                    flags.append(flag)
                    if flag == '-i':
                        flags.append('-i'+str(private))
            flags += ['-odir',str(out/'objects'),'-hidir',str(out/'objects')]
            binary = out/'diagnostic-emlf'
            command = [authenticated['ghc']['path'],'--make','-j1',*flags,
                       '-I'+str(source/'runtime'),'-rtsopts=ignoreAll',
                       str(private/'Main.hs'), str(source/'host/ghc/cbits/host.c'),
                       str(source/'runtime/mlf_process_supervisor.c'),'-o',str(binary)]
            record['producer'] = str(producer)
            record['copied_ordinary_objects'] = copied
            record['commands'].append(H.Runner(out,LIMITS).run(command,source,out/'build'))
            for path in [owner,private/'KindCounters.hs',private/'Main.hs',binary]:
                pins[str(path)] = H.sha(path)
            queries = out/'queries'
            queries.mkdir()
            fields = ['MLF-CRATE-1','full-compiler/current',workload['entry'],'false',
                      pack([pack([row['module'],row['source']])
                            for row in sorted(workload['modules'],key=lambda row:row['module'])]),
                      pack([setup['builtin']+'.mlfci']),str(queries),setup['builtin']]
            spec = out/'crate.spec'
            spec.write_text(pack(fields))
            pins[str(spec)] = H.sha(spec)
            record['inputs'] = pins
            save()
            # Keep this one mechanism run separate from optional query clocks.
            for name in ['MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT']:
                os.environ.pop(name,None)
            command = [str(binary),'--compile-crate',str(spec),'-o',str(out/'unit')]
            record['commands'].append(H.Runner(out,LIMITS).run(command,source,out/'run'))
            raw = (out/'run/stderr').read_text()
            H.require(raw.startswith('KIND_DIAGNOSTIC ') and raw.count('\n') == 1,
                      'unexpected diagnostic stderr')
            counts = json.loads(raw[len('KIND_DIAGNOSTIC '):])
            H.require(set(counts) == {'roots','recursive_visits','unique_variable_roots',
                                     'max_visits_per_root','roots_with_repeats'} and
                      all(type(value) is int and value >= 0 for value in counts.values()),
                      'malformed diagnostic counters')
            H.require(counts['recursive_visits'] >= counts['unique_variable_roots'] and
                      counts['roots'] >= counts['roots_with_repeats'], 'invalid count totals')
            current, prior = H.load(out/'unit.queries'), H.load(str(reference)+'.queries')
            groups = lambda value: [{key:group[key] for key in ['id','members']}
                                     for group in value['groups']]
            H.require(current['reused_groups'] == 0 and
                      current['inferred_groups'] == len(current['groups']) > 0 and
                      all(group['cached'] is False for group in current['groups']),
                      'diagnostic did not infer every group freshly')
            H.require(groups(current) == groups(prior), 'ordered group identity changed')
            artifacts = {}
            for extension in ['.mlfci','.mlfco']:
                result = out/('unit'+extension)
                H.require(same_bytes(result,Path(str(reference)+extension)),
                          'checked artifact differs: '+extension)
                artifacts[str(result)] = H.sha(result)
            H.check_pins(pins)
            H.require(H.authenticate(producer,source) == authenticated, 'producer changed')
            record.update(complete=True, counts=counts, inferred_groups=current['inferred_groups'],
                          reused_groups=0, checked_raw_bytes_equal=True,
                          ordered_groups_equal=True, artifacts=artifacts)
            save()
            print(json.dumps(counts,sort_keys=True))
    except BaseException as error:
        record['error'] = repr(error)
        save()
        raise


if __name__ == '__main__':
    main()
