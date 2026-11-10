#!/usr/bin/env python3
"""Capture ordinary Bootstrap.Graph owner codegen after exact F3 semantics pass.

This never links a compiler or runs a benchmark. Capture success is not a
mechanism/throughput pass: independent caller/allocation review remains required.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / 'compiler-baseline-20261110'
CANDIDATE_ROOT = ROOT / 'compiler-graph-read-fusion-20261110'
OWNER = 'libraries/mlf-inference/Bootstrap/Graph.hs'
ORIGINAL = '9df4833f55f0826181f8e1e974dc0672753e9462de0d134f64fc3f8c6f6e8a7f'
CANDIDATE = 'fdb9e899392ac0068f9f11432d512d1168934455a6da733a10e7cabb52d19df3'
PRODUCER = SOURCE / '.mlf-build/baseline-producer'
PRODUCER_RECEIPT = 'b71bbb5ebb757a206ed41932cdafca982f1e7246218496953be273afad5a8caf'
ANCHOR_OBJECT = 'ebe745b5d50f8dfc113e252bff8dc726716e45125ae75857d6965e181c050e20'
ANCHOR_INTERFACE = '0e0721158f1c6c7f4bdf46577c3a964f377efcd827cb87c7718945ee12bb4c63'
SEMANTICS = CANDIDATE_ROOT / 'tools/performance/graph-read-fusion'
SEMANTIC_PINS = {
    'run.py': '2d1fd99be0a83c147273ce338df9714da19f40f9eef615769d95c789a0bb3fbd',
    'Main.hs': '70e98445bb413fb5938419919dcb1567732a02eef400d151a5c4b589f7d9ea97',
    'ReadDemand.hs': '87c30e3af4e433781e7aa5725271f26fdf7862100a607dcc3c8ceb6b6328117d',
    'sites.json': 'b77585e3b5acd68b3ac8cd475350b6ae913ed3bf6f2da2462c7d31c2482f600f'}
LIMITS = dict(address_space_per_process_bytes=6*1024**3, process_tree_rss_bytes=5*1024**3,
              host_available_floor_bytes=3*1024**3, disk_free_floor_bytes=5*1024**3,
              max_work_bytes=4*1024**3, wall_seconds=180)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--semantics', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args(); out = a.output.resolve(); semantic_output = a.semantics.resolve()
    out.mkdir(parents=True, exist_ok=False); started = time.monotonic()
    helper = SOURCE / 'tools/performance/a1-private-index/helper.py'
    scope = SOURCE / 'tools/performance/process-spawn/with_scope.py'
    watchdog = SOURCE / 'tools/shared/resource_watchdog.py'
    H = types.ModuleType('codegen_guard'); H.__file__ = str(helper)
    exec(compile(helper.read_bytes(), str(helper), 'exec'), H.__dict__)
    record = dict(complete=False, source_commit='f9bdb40a659bfdff4cbb782d438afbb0417dd2e1',
                  capture_only=True, mechanism_review='pending', performance_admitted=False,
                  compiler_producer_build=False, benchmark_samples=[], commands=[], sides={})
    save = lambda: H.save(out / 'receipt.json', record)
    save()
    def run(label, argv):
        remaining = 180 - (time.monotonic() - started)
        H.require(remaining > 0, 'shared owner-codegen deadline exhausted')
        result = H.Runner(out, {**LIMITS, 'wall_seconds': remaining}).run(
            [sys.executable, '-B', scope, *argv], SOURCE, out / label)
        record['commands'].append(dict(label=label, resource=result)); save()
        return out / label
    try:
        with H.SerialLock(SOURCE / '.mlf-build'):
            for key in list(os.environ):
                if key.startswith(('MLF_DIAGNOSTIC_', 'MLF_COST_CENTRE_')) or key in (
                        'MLF_QUERY_PROFILE', 'MLF_QUERY_SEMANTIC_AUDIT', 'MLF_QUERY_FAILPOINT'):
                    del os.environ[key]
            pins = {str(SOURCE / OWNER): ORIGINAL, str(CANDIDATE_ROOT / OWNER): CANDIDATE,
                    str(PRODUCER / 'receipt.json'): PRODUCER_RECEIPT,
                    str(PRODUCER / 'objects/Bootstrap/Graph.o'): ANCHOR_OBJECT,
                    str(PRODUCER / 'objects/Bootstrap/Graph.hi'): ANCHOR_INTERFACE}
            pins.update({str(SEMANTICS / name): digest for name, digest in SEMANTIC_PINS.items()})
            for path in [Path(__file__), HERE / 'run-gate.sh', helper, scope, watchdog]: pins[str(path)] = sha(path)
            H.check_pins(pins)
            auth = H.authenticate(PRODUCER, SOURCE)
            sem_scope = semantic_output / 'scope/command.json'; sem = H.load(sem_scope)
            H.require(sem.get('complete') is True and sem.get('exit_code') == 0 and not sem.get('reason')
                      and not sem.get('terminal_live_descendants'), 'F3 outer semantics scope failed/incomplete')
            H.require(sem['limits']['wall_seconds'] == 240, 'wrong semantics budget identity')
            pins[str(sem_scope)] = sha(sem_scope)
            for optimization in ['0', '2']:
                directory = semantic_output / ('O' + optimization)
                path = directory / 'receipt.json'; receipt = H.load(path)
                H.require(receipt.get('complete') is True and receipt.get('optimization') == optimization,
                          'both exact O0/O2 semantics receipts required')
                H.require(receipt.get('performance_samples') == [] and receipt.get('compiler_producer_build') is False,
                          'gate-only semantics required')
                H.require(receipt['inputs'].get(str(CANDIDATE_ROOT / OWNER)) == CANDIDATE,
                          'semantics candidate differs')
                for name, digest in SEMANTIC_PINS.items():
                    H.require(receipt['inputs'].get(str(SEMANTICS / name)) == digest, 'semantic owner identity mismatch')
                H.check_pins(receipt['inputs']); H.check_pins(receipt['borrowed_objects'])
                H.require(sha(directory / 'controls-probe') == receipt['executable_sha256'], 'semantic binary changed')
                H.require(all(row.get('complete') is True for row in receipt['commands']), 'semantic command failure')
                pins[str(path)] = sha(path)
            record['semantic_receipts'] = {str(path): pins[str(path)] for path in
                [sem_scope, semantic_output / 'O0/receipt.json', semantic_output / 'O2/receipt.json']}

            dependencies = out / 'dependencies'; dependencies.mkdir()
            borrowed = {}
            for relative, digest in auth['object_inputs'].items():
                if relative.startswith('objects/') and relative.endswith('.hi') and relative not in (
                        'objects/Bootstrap/Graph.hi', 'objects/Main.hi'):
                    target = dependencies / Path(relative).relative_to('objects')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(PRODUCER / relative, target)
                    H.require(sha(target) == digest, 'borrowed ordinary interface changed')
                    borrowed[str(target)] = digest
            tools = {}
            for name in ['objdump', 'nm', 'size']:
                found = shutil.which(name); H.require(found is not None, 'missing trusted binutils ' + name)
                tools[name] = str(Path(found).resolve()); pins[tools[name]] = sha(tools[name])
            common = []; skip = False
            for flag in auth['flags']:
                if skip: skip = False; continue
                if flag in ['-odir', '-hidir']: skip = True
                elif flag.startswith('-i'): continue
                else: common.append(flag)
            H.require(all(flag in common for flag in ['-O2', '-fpedantic-bottoms', '-fno-state-hack']), 'ordinary flags required')
            H.require(not any(flag in common for flag in ['-prof', '-fstate-hack']), 'non-ordinary flags forbidden')
            common += ['-i', '-i' + str(dependencies)]
            record.update(inputs=pins, borrowed_interfaces=borrowed, tools=tools, common_flags=common,
                          dump_only_flags=['-ddump-to-file', '-ddump-simpl', '-ddump-cmm-raw'],
                          authentication=auth); save()
            for name, executable in tools.items(): run('version-' + name, [executable, '--version'])

            def capture(side, obj, interface):
                dis = run(side + '-objdump', [tools['objdump'], '-dr', obj])
                symbols = run(side + '-nm', [tools['nm'], '-S', obj])
                size = run(side + '-size', [tools['size'], '-A', obj])
                iface = run(side + '-iface', [auth['ghc']['path'], '--show-iface', interface])
                text = (dis / 'stdout').read_text(); symbol_text = (symbols / 'stdout').read_text()
                interface_text = (iface / 'stdout').read_text()
                H.require('interface Bootstrap.Graph ' in interface_text, 'not original Graph module identity')
                H.require(not re.search(r'(CandidateGraph|LegacyGraph)', symbol_text), 'renamed semantic object is not production codegen')
                H.require('BootstrapziGraph_readDense_info' in symbol_text, 'public helper missing')
                return dict(object=str(obj), object_sha256=sha(obj), interface=str(interface), interface_sha256=sha(interface),
                    disassembly=str(dis / 'stdout'), symbols=str(symbols / 'stdout'), sections=str(size / 'stdout'),
                    interface_dump=str(iface / 'stdout'),
                    direct_readDense_jumps=len(re.findall(r'\bjmp\s+[0-9a-f]+\s+<BootstrapziGraph_readDense_info>', text)),
                    readDense_reference_lines=[line for line in text.splitlines() if 'BootstrapziGraph_readDense' in line],
                    allocation_claim='none; independent caller/Core/Cmm review required')
            record['sides']['anchor'] = capture('anchor', PRODUCER / 'objects/Bootstrap/Graph.o', PRODUCER / 'objects/Bootstrap/Graph.hi'); save()
            for side, source in [('baseline', SOURCE / OWNER), ('candidate', CANDIDATE_ROOT / OWNER)]:
                directory = out / side; objects = directory / 'objects'; objects.mkdir(parents=True)
                (objects / 'Bootstrap').mkdir(); dumps = directory / 'dumps'; dumps.mkdir()
                obj = objects / 'Bootstrap/Graph.o'; interface = objects / 'Bootstrap/Graph.hi'
                flags = [*common, '-odir', str(objects), '-hidir', str(objects), '-ohi', str(interface),
                         '-fforce-recomp', '-v', '-ddump-to-file', '-ddump-simpl', '-ddump-cmm-raw',
                         '-ddump-file-prefix=' + str(dumps / 'Graph')]
                run(side + '-compile', [auth['ghc']['path'], *flags, '-c', source, '-o', obj])
                H.require(obj.is_file() and interface.is_file(), 'fresh owner output missing')
                H.require((dumps / 'Graph.dump-simpl').is_file() and (dumps / 'Graph.dump-cmm-raw').is_file(), 'required caller dumps missing')
                record['sides'][side] = capture(side, obj, interface)
                record['sides'][side].update(flags=flags, source=str(source),
                    core=str(dumps / 'Graph.dump-simpl'), cmm=str(dumps / 'Graph.dump-cmm-raw'))
                save()
            H.check_pins(pins); H.check_pins(borrowed)
            H.require(H.authenticate(PRODUCER, SOURCE) == auth, 'ordinary producer changed')
            H.require(time.monotonic() - started < 180, 'shared capture budget exhausted')
            outputs = {}
            for path in out.rglob('*'):
                if path.is_file() and path != out / 'receipt.json' and not path.is_relative_to(dependencies):
                    outputs[str(path)] = sha(path)
            record.update(complete=True, output_pins=outputs, elapsed_seconds=time.monotonic() - started)
            save()
    except BaseException as error:
        record.update(error=repr(error), elapsed_seconds=time.monotonic() - started); save(); raise


if __name__ == '__main__': main()
