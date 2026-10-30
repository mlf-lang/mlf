#!/usr/bin/env python3
"""Finite fixed-14 correctness qualification. No performance estimate/cohort."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools/performance/a1-private-index'))
import helper as H
import reproduce as R

LIMITS = dict(process_tree_rss_bytes=5*1024**3,
              address_space_per_process_bytes=6*1024**3,
              host_available_floor_bytes=3*1024**3,
              disk_free_floor_bytes=4*1024**3,
              max_work_bytes=16*1024**3, wall_seconds=21600)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--controls-receipt', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    controls_path = a.controls_receipt.resolve(strict=True)
    gate = H.load(controls_path)
    H.require(gate['format'] == 'c4-full-current-controls-v1', 'full two-producer controls required')
    for name in ['complete','all_controls_passed','full_gate_passed','focused_graph_gate_passed',
                 'nine_file_comparison_passed','builtin_admission_passed','immutable_inputs_verified_after']:
        H.require(gate[name] is True, 'missing prerequisite: ' + name)
    H.require(len(gate['file_cases']) == 9, 'nine independently authored file controls')
    sources = {k: Path(v).resolve(strict=True) for k,v in gate['source_roots'].items()}
    producers = {k: Path(v).resolve(strict=True) for k,v in gate['producers'].items()}
    H.require(set(sources) == set(producers) == {'base','candidate'}, 'exact producer pair')
    H.require(sources['candidate'] == ROOT, 'candidate-owned qualification script')
    out = a.output.absolute()
    H.require(not os.path.lexists(out), 'fresh output; reject dangling links and retain every failed attempt')
    out = out.resolve()
    for root in [*sources.values(), *producers.values(), controls_path.parent]:
        H.require(not out.is_relative_to(root) and not root.is_relative_to(out), 'disjoint output')
    H.check_pins(gate['inputs']); H.check_pins(gate['outputs'])
    pins = {str(controls_path): H.sha(controls_path), str(Path(__file__)): H.sha(__file__)}
    originals = {}
    for side in ['base','candidate']:
        producer = producers[side]
        H.require(H.sha(producer/'receipt.json') == gate['producer_receipt_sha256'][side], 'same ordinary producer')
        originals[side] = H.authenticate(producer, sources[side])
        pins[str(producer/'receipt.json')] = H.sha(producer/'receipt.json')
    for field in ['ghc','cc','installed_dependencies','ghc_settings','toolchain']:
        H.require(originals['base'][field] == originals['candidate'][field], 'same actual toolchain ' + field)
    data, fixture_pins = R.fixture_contract()
    pins.update(fixture_pins)
    builtin = Path(gate['shared_builtin_prefix']).resolve()
    for suffix in R.SUFFIXES:
        path = str(builtin) + suffix
        H.require(path in gate['inputs'] and H.sha(path) == gate['inputs'][path], 'admitted immutable common builtin')
        pins[path] = H.sha(path)
    def stable_host():
        observed = H.host()
        selected = {k:observed[k] for k in ['platform','machine','node','affinity','cgroup','python']}
        selected['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return selected
    initial_host = stable_host()
    H.require(all(initial_host[k] == gate['host'][k] for k in initial_host if k != 'boot_id'),
              'same host/configuration as full controls')
    out.mkdir(parents=True)
    record = dict(format='c4-fixed14-current-correctness-v1', complete=False,
                  performance_measured=False, timing_speedup_claimed=False, host=H.host(),
                  controls_receipt_sha256=H.sha(controls_path), source_roots=gate['source_roots'],
                  producers=gate['producers'], producer_receipt_sha256=gate['producer_receipt_sha256'],
                  builtin_representation='current canonical literal independently admitted by full controls; not historical P3 byte identity',
                  inputs=pins, limits=LIMITS, stable_host=initial_host,
                  provider_steps=[], target_steps=[], commands=[])
    def save(): H.save(out/'receipt.json', record)
    def unchanged():
        H.require(stable_host() == initial_host, 'host/boot/affinity changed; never splice machines')
        H.check_pins(pins); H.check_pins(gate['inputs']); H.check_pins(gate['outputs'])
        for side in ['base','candidate']:
            H.require(H.authenticate(producers[side],sources[side]) == originals[side], 'producer drift')
    save()
    with H.SerialLock(out.parent):
        runner = H.Runner(out, LIMITS)
        try:
            # Six immutable historical provider sources; no historic builtin-hash
            # substitution. The supplied current pair was structurally admitted
            # independently before this script can create any provider or target.
            deps = out/'dependencies'; deps.mkdir()
            prefixes = {name: deps/name/'unit' for name in R.PROVIDERS}
            artifacts = {str(builtin)+suffix: H.sha(str(builtin)+suffix) for suffix in R.SUFFIXES}
            for provider in data['providers']:
                name = provider['name']; folder = deps/name; folder.mkdir()
                dependencies = [Path(str(prefixes[k])+'.mlfci') for k in provider['dependencies']]
                spec = folder/'crate.spec'; queries = folder/'queries'
                R.crate_spec(spec,name+'/'+provider['version']+'/library',provider['modules'],dependencies,queries,builtin)
                record['commands'].append(runner.run([producers['base']/'bin/emlf','--compile-crate',spec,'-o',prefixes[name]],folder,folder/'command'))
                query = R.validate_query(Path(str(prefixes[name])+'.queries'))
                H.require(query['inferred_groups'] > 0, 'nonempty fresh provider')
                H.check_pins(artifacts); artifacts.update(R.artifacts(prefixes[name]))
                record['provider_steps'].append(dict(name=name,query=query,artifacts=R.artifacts(prefixes[name])))
                unchanged(); save()
            H.require(len(artifacts) == 14, 'six provider pairs plus shared builtin')
            dependencies = dict(complete=True,artifacts=artifacts,
                                provider_prefixes={k:str(v) for k,v in prefixes.items()},
                                target_dependencies=[str(prefixes[k])+'.mlfci' for k in data['target_dependencies']],
                                builtin_prefix=str(builtin))
            H.save(deps/'receipt.json', dependencies)
            # Unchanged independent seven-object reload, raw target rechecking,
            # and malformed object rejection. Never replace this with hashes.
            R.validate_dependencies(out,sources['base'],producers['base'],data,dependencies,runner)
            record['independent_dependency_validation_passed'] = True; save()
            ghc = R.prepare_ghc(out, Path(originals['base']['ghc']['path']), data, runner)
            reference = None
            for side in ['base','candidate']:
                unchanged(); H.check_pins(artifacts)
                folder = out/('target-'+side); folder.mkdir()
                spec=folder/'crate.spec'; queries=folder/'queries'
                fields=R.crate_spec(spec,data['target']['crate_id'],data['target']['modules'],dependencies['target_dependencies'],queries,builtin)
                H.save(folder/'spec-fields.json',fields)
                H.require(not queries.exists(), 'target inference cache absent')
                command=runner.run([producers[side]/'bin/emlf','--compile-crate',spec,'-o',folder/'unit'],folder,folder/'command')
                query=R.validate_query(folder/'unit.queries',data)
                query_files = list(queries.iterdir())
                H.require(len(query_files) == 544 and all(p.is_file() and not p.is_symlink() and p.suffix == '.mlfq'
                                                        for p in query_files),
                          'exactly 544 regular non-symlink newly materialized query files')
                current={suffix:Path(str(folder/'unit')+suffix).read_bytes() for suffix in R.SUFFIXES}
                if reference is None: reference=current
                H.require(current == reference, 'complete raw checked byte equality, no normalization')
                record['target_steps'].append(dict(side=side,command=command,inferred_groups=544,reused_groups=0,
                    target_cache_initially_absent=True,new_query_files=544,exact_fixed_projection=True,
                    byte_identical_to_current_before=True,query_sha256=H.sha(folder/'unit.queries'),
                    artifacts={k:hashlib.sha256(v).hexdigest() for k,v in current.items()}))
                unchanged(); H.check_pins(artifacts); save()
            folder=out/'target-GHC';folder.mkdir();objects=folder/'objects'
            shutil.copytree(ghc['reusable_directory'],objects)
            H.require(len(H.file_pins(objects)) == 112, '56 reusable dependencies only')
            command=runner.run(R.ghc_argv(ghc['ghc'],objects,data),folder,folder/'command')
            rows=R.compiled(folder/'command')
            expected={n:H.below(R.FIXTURES,row['path']) for n,row in data['target']['modules'].items()}
            H.require(len(rows)==14 and dict(rows)==expected,'exact 14 fresh GHC targets; no dependency rebuild')
            H.check_pins({str(objects/rel):sha for rel,sha in ghc['reusable_dependency_files'].items()})
            record['ghc_control']=dict(command=command,fresh_target_modules=14,reused_dependency_modules=56)
            unchanged();H.check_pins(artifacts)
            record.update(complete=True,raw_checked_byte_comparison_passed=True,immutable_inputs_verified_after=True,
                          stable_host_after=stable_host(),
                          outputs={str(p):H.sha(p) for p in out.rglob('*') if p.is_file() and p != out/'receipt.json'})
        except BaseException as e:
            record['error']=repr(e);raise
        finally: save()
    print('PASS C4 current fixed14: 544/0 each, shared dependencies, raw checked bytes, 14 fresh GHC modules; no performance estimate')


if __name__ == '__main__': main()
