#!/usr/bin/env python3
"""Logical traversal diagnostic. No ordinary performance timings are measured."""
from pathlib import Path
import argparse
import json
import shutil
import types

import instrument
from instrument import require

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_PRODUCER = ROOT / '.mlf-build/owned-reservation-20261101/producer'
DEFAULT_CONFIG = ROOT / '.mlf-build/owned-reservation-20261101/curve-config.json'


def event(rows, key):
    return rows.get(key, {}).get('events', 0)


def validate_counts(rows):
    require(rows and all(set(row) == {'events', 'depth_sum', 'max_depth'} for row in rows.values()),
            'complete counter row schema required')
    require(all(row['events'] > 0 and 0 <= row['max_depth'] <= row['depth_sum'] for row in rows.values()),
            'positive event totals and consistent depths required')
    for family in ('commonCalls', 'substituteUsed'):
        require(event(rows, family + '.visits') == event(rows, family + '.pruned') + event(rows, family + '.positive'), family)
    for origin in {key.rsplit('.', 1)[0] for key in rows if key.startswith('copy.')}:
        visits = event(rows, origin + '.visits')
        branches = sum(event(rows, origin + '.' + kind) for kind in
                       ('variable_lookup', 'rebuild_abs', 'rebuild_app', 'rebuild_let', 'rebuild_rec', 'rebuild_case', 'reuse_leaf'))
        require(visits == branches and event(rows, origin + '.roots') <= visits, origin)
    require(not event(rows, 'copy.other.roots'), 'an unclassified production copy root executed')


def validate_output(ordinary, diagnostic):
    require(ordinary.read_bytes() == diagnostic.read_bytes(), 'ordinary/diagnostic LLVM differs')


def unpack_fields(text):
    """Separate.unpack framing, for dependency discovery only, not admission."""
    fields, start = [], 0
    while start < len(text):
        end = text.find(':', start)
        digits = text[start:end] if end >= 0 else ''
        require(1 <= len(digits) <= 9 and all('0' <= char <= '9' for char in digits),
                'malformed artifact length framing')
        size = int(digits)
        require(size <= len(text) - end - 1, 'truncated artifact field')
        fields.append(text[end + 1:end + 1 + size])
        start = end + 1 + size
    return fields


def checked_closure(roots):
    """Pin the complete graph that CrateArtifact.loadGraph/linkCheckedFile read.

    Production decodeInterface/decodeObject still check checksums and semantics.
    This parser only discovers paths using their exact MLFCI-5 framing.
    """
    pins, graph, visiting = {}, {}, set()
    def visit(requested):
        path = Path(requested).resolve(strict=True)
        require(path.suffix == '.mlfci' and path.is_file(), 'regular checked interface required')
        require(path not in visiting, 'cyclic checked dependency closure')
        if str(path) in graph:
            return
        visiting.add(path)
        raw = path.read_bytes()
        fields = unpack_fields(raw.decode('utf-8'))
        require(len(fields) == 14 and fields[0] == 'MLFCI-5', 'unsupported checked interface framing')
        pins[str(path)] = instrument.sha(raw)
        object_path = path.with_suffix('.mlfco')
        require(object_path.is_file() and object_path.resolve() == object_path, 'regular checked object required')
        pins[str(object_path)] = instrument.sha(object_path.read_bytes())
        dependencies = []
        for encoded in unpack_fields(fields[2]):
            parts = unpack_fields(encoded)
            require(len(parts) == 3 and parts[0] and parts[2] and Path(parts[1]).is_absolute(),
                    'malformed checked dependency')
            dependency = Path(parts[1]).resolve(strict=True)
            dependencies.append(str(dependency))
            visit(dependency)
        graph[str(path)] = dependencies
        visiting.remove(path)
    for root in roots:
        visit(root)
    return pins, graph


def validate_object_inventory(producer, auth, pins):
    inventory = {str(Path(path).relative_to(producer)): digest for path, digest in pins.items()}
    require(inventory == auth['object_inputs'], 'exact authenticated producer object inventory required')


def validate_workload_counts(rows):
    validate_counts(rows)
    for family in ('commonCalls', 'substituteUsed', 'identities', 'indexUses', 'passRaw'):
        require(event(rows, family + '.roots') > 0 and event(rows, family + '.visits') > 0,
                'missing demanded workload traversal: ' + family)
    for origin in ('initial_uniqueness', 'final_numbering'):
        require(event(rows, 'copy.' + origin + '.roots') > 0, 'missing required copy origin: ' + origin)


def validate_controls(result):
    require(result['complete'] is True, 'controls did not complete')
    for name, family in [('zero_substitute', 'substituteUsed'), ('zero_common', 'commonCalls')]:
        rows = result[name]
        require(set(rows) == {family + '.' + part for part in ('roots', 'visits', 'pruned')},
                'exact zero-use counter labels: ' + name)
        require(all(row == {'events': 1, 'depth_sum': 0, 'max_depth': 0} for row in rows.values()),
                'exact zero-use event counts and depths: ' + name)
    positive = {
        'positive_common': {
            'commonCalls.roots': (1, 0, 0), 'commonCalls.visits': (3, 2, 1),
            'commonCalls.positive': (2, 1, 1), 'commonCalls.pruned': (1, 1, 1),
            'useApplications.roots': (2, 0, 0), 'useApplications.visits': (4, 2, 1),
        },
        'positive_substitute': {
            'substituteUsed.roots': (1, 0, 0), 'substituteUsed.visits': (5, 6, 2),
            'substituteUsed.positive': (3, 3, 2), 'substituteUsed.pruned': (2, 3, 2),
            'substituteUsed.rebuild_parent': (2, 1, 1),
            'copy.substitute.roots': (1, 0, 0), 'copy.substitute.visits': (2, 1, 1),
            'copy.substitute.rebuild_abs': (1, 0, 0), 'copy.substitute.variable_lookup': (1, 1, 1),
            'copy.substitute.fresh_binder': (1, 0, 0),
            'indexUses.roots': (1, 0, 0), 'indexUses.visits': (2, 1, 1),
        },
    }
    for name, expected_rows in positive.items():
        validate_counts(result[name])
        expected = {key: dict(zip(('events', 'depth_sum', 'max_depth'), values))
                    for key, values in expected_rows.items()}
        require(result[name] == expected, 'exact positive traversal control: ' + name)
    rows = result['alias']
    validate_counts(rows)
    expected = {'roots': 1, 'visits': 4, 'variable_lookup': 2, 'rebuild_abs': 1, 'rebuild_app': 1, 'fresh_binder': 1}
    require({key.removeprefix('copy.identities_alias.'): row['events'] for key, row in rows.items()
            if key.startswith('copy.identities_alias.')} == expected, 'exact alias copy branch counts')
    require(rows['copy.identities_alias.visits']['max_depth'] == 2, 'exact alias copy maximum depth')
    require(rows['copy.identities_alias.visits']['depth_sum'] == 5, 'exact alias copy depth sum')
    require(event(rows, 'identities.visits') == 6, 'exact identities node visits')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--producer', type=Path, default=DEFAULT_PRODUCER)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    dest, producer, config_path = args.output.resolve(), args.producer.resolve(), args.config.resolve()
    scratch = (ROOT / '.mlf-build/inline-traversals-20261101').resolve()
    require(dest.is_relative_to(scratch) and dest != scratch and not dest.exists(), 'fresh child of dedicated scratch required')
    require(not dest.is_relative_to(producer) and not producer.is_relative_to(dest), 'independent producer and diagnostic directories required')
    helper = ROOT / 'tools/performance/a1-private-index/helper.py'
    H = types.ModuleType('guard')
    H.__file__ = str(helper)
    exec(compile(helper.read_bytes(), str(helper), 'exec'), H.__dict__)
    dest.mkdir(parents=True)
    record = {'complete': False, 'purpose': 'logical demanded traversals; not timing or physical allocation', 'commands': []}
    save = lambda: H.save(dest / 'receipt.json', record)
    save()
    try:
        with H.SerialLock(ROOT / '.mlf-build'):
            auth = H.authenticate(producer, ROOT)
            producer_pins = H.file_pins(producer / 'objects')
            validate_object_inventory(producer, auth, producer_pins)
            config = H.load(config_path)
            cases = []
            for family in ('dependency_chain', 'inferred_chain'):
                for size in (32, 128, 512, 2048):
                    key = f'{family}-{size}'
                    prefix = Path(config['references'][key]['prefix'])
                    cases.append({'case': key, 'family': family, 'size': size,
                                  'interface': str(prefix) + '.mlfci', 'object': str(prefix) + '.mlfco'})
            closure_pins, closure_graph = checked_closure(case['interface'] for case in cases)
            original_optimize = ROOT / 'libraries/mlf-llvm/Bootstrap/LLVM/Optimize.hs'
            original_llvm = ROOT / 'libraries/mlf-llvm/Bootstrap/LLVM.hs'
            transformed_optimize, optimize_edits = instrument.optimize(original_optimize.read_bytes())
            transformed_llvm, llvm_edits = instrument.llvm(original_llvm.read_bytes())
            private_optimize, private_llvm = dest / 'DiagnosticOptimize.hs', dest / 'DiagnosticLLVM.hs'
            private_optimize.write_bytes(transformed_optimize)
            private_llvm.write_bytes(transformed_llvm)
            H.save(dest / 'reversible-transformations.json', {'Optimize': optimize_edits, 'LLVM': llvm_edits})
            inputs = [helper, ROOT / 'tools/shared/test_direct.py', config_path,
                      producer / 'host.o', producer / 'supervisor.o',
                      ROOT / 'libraries/mlf-crates/Bootstrap/CrateArtifact.hs',
                      ROOT / 'libraries/mlf-crates/Bootstrap/Separate.hs',
                      original_optimize, original_llvm, private_optimize, private_llvm,
                      *sorted(HERE.glob('*.py')), *sorted(HERE.glob('*.hs')),
                      *(Path(case[field]) for case in cases for field in ('interface', 'object'))]
            pins = {str(path): H.sha(path) for path in inputs}
            pins.update(closure_pins)
            H.check_pins(pins)
            record.update(inputs=pins, cases=cases, producer=str(producer),
                          checked_dependency_graph=closure_graph, producer_object_inventory=producer_pins,
                          producer_receipt_sha256=H.sha(producer / 'receipt.json'),
                          transformations={'exactly_reversible': True, 'ledger': str(dest / 'reversible-transformations.json')})
            save()
            objects = dest / 'objects'
            shutil.copytree(producer / 'objects', objects)
            for suffix in ('.o', '.hi'):
                (objects / ('Main' + suffix)).unlink(missing_ok=True)
            local_pins = H.file_pins(objects)
            expected_copied = {str(objects / Path(path).relative_to(producer / 'objects')): digest
                               for path, digest in producer_pins.items()
                               if Path(path).relative_to(producer / 'objects').as_posix() not in ('Main.o', 'Main.hi')}
            require(local_pins == expected_copied, 'copied authentic object inventory differs')
            flags, oldflags, index = [], list(auth['flags']), 0
            while index < len(oldflags):
                flag = oldflags[index]
                if flag in ('-odir', '-hidir'):
                    index += 2
                    continue
                if flag.startswith('-i'):
                    index += 1
                    continue
                flags.append(flag)
                index += 1
            flags += ['-fno-cse', '-fno-full-laziness', '-i', '-i' + str(objects),
                      '-odir', str(objects), '-hidir', str(objects)]
            limits = {'address_space_per_process_bytes': 6 * 1024**3, 'disk_free_floor_bytes': 5 * 1024**3,
                      'host_available_floor_bytes': 3 * 1024**3, 'max_work_bytes': 2 * 1024**3,
                      'process_tree_rss_bytes': 5 * 1024**3, 'wall_seconds': 600}
            def run(name, argv):
                result = H.Runner(dest, limits).run(argv, ROOT, dest / name, timed=False)
                record['commands'].append(result)
                save()
            ghc = auth['ghc']['path']
            for name, source in [('counter-build', HERE / 'Counters.hs'), ('optimize-build', private_optimize),
                                 ('llvm-build', private_llvm), ('main-build', HERE / 'Main.hs')]:
                run(name, [ghc, *flags, '-c', str(source)])
            H.check_pins(local_pins)
            executable = dest / 'inline-traversals'
            run('link', [ghc, *flags, *map(str, sorted(objects.rglob('*.o'))),
                         str(producer / 'host.o'), str(producer / 'supervisor.o'), '-o', str(executable)])
            controls = []
            for repeat in (1, 2):
                name = f'controls-{repeat}'
                run(name, [str(executable), '--controls'])
                require(not (dest / name / 'stderr').read_bytes(), "required invariant: not (dest / name / 'stderr').read_bytes()")
                value = json.loads((dest / name / 'stdout').read_text())
                validate_controls(value)
                controls.append(value)
            require(controls[0] == controls[1], 'fixed controls have nondeterministic events')
            record['controls'] = {'complete': True, 'identical_repeats': 2, 'counts': controls[0]}
            save()
            results = []
            for case in cases:
                name = case['case']
                output = dest / (name + '-artifacts')
                output.mkdir()
                run(name, [str(executable), case['interface'], str(output)])
                require(not (dest / name / 'stderr').read_bytes(), "required invariant: not (dest / name / 'stderr').read_bytes()")
                value = json.loads((dest / name / 'stdout').read_text())
                require(value['complete'] is True, "required invariant: value['complete'] is True")
                validate_workload_counts(value['counters'])
                ordinary, diagnostic = output / 'ordinary.ll', output / 'diagnostic.ll'
                validate_output(ordinary, diagnostic)
                value.update(case=case, llvm_sha256=H.sha(ordinary), llvm_bytes=ordinary.stat().st_size,
                             exact_ordinary_llvm_equal=True)
                results.append(value)
                H.save(dest / 'counts.json', results)
                print(name, 'exact_ordinary_llvm_equal=true', flush=True)
            H.check_pins(pins)
            H.check_pins(producer_pins)
            validate_object_inventory(producer, auth, H.file_pins(producer / 'objects'))
            H.require(H.authenticate(producer, ROOT) == auth, 'ordinary producer changed')
            record.update(complete=True, results=str(dest / 'counts.json'))
            save()
    except BaseException as exc:
        record['error'] = repr(exc)
        save()
        raise


if __name__ == '__main__':
    main()
