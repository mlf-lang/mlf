"""Exercise dependency preference through a real package build and native link."""
import json
from pathlib import Path

from test_direct import dependency_diagnostics, sha
from source_root_cli import UNIFIED_SOURCE


def check_package_dependencies(runner, tools, root, clang, gc):
    work = runner.root

    def manifest(name, **fields):
        directory = work / name
        directory.mkdir()
        data = dict(format=1, name=name, version='0.1.0', **fields)
        path = directory / 'mlf-package.json'
        path.write_text(json.dumps(data) + '\n')
        return path

    def check(condition, message):
        if not condition:
            raise ValueError(message)

    runner_path = work / 'mlf-build-runner'
    runner.run('package-runner', [clang, '-O2', '-std=c11', root / 'runtime/mlf_build_runner.c',
                                 '-o', runner_path])
    release = work / 'checked-release'
    shared = work / 'cache'
    exe = work / 'build/bin/mixed'
    compiler = tools / 'emlf'
    manager = tools / 'mlfpkg'

    def package(name, source, cache, directory, *action):
        result = runner.run(name, [manager, '--manifest', source, '--compiler', compiler, '--clang', clang,
                            '--gc-prefix', gc, '--runtime', root / 'runtime/mlf_runtime.c',
                            '--build-dir', directory, '--cache-dir', cache, '--jobs', '1', *action],
                            overrides={'MLF_BUILD_RUNNER': str(runner_path)}, timeout=300)
        check(b'dependency ' not in result.stdout, 'package command wrote dependency choices to stdout')
        return directory / 'build-report.json'

    sealed = manifest('sealed', library={'modules': {'Sealed': 'Sealed.emlf'}})
    (sealed.parent / 'Sealed.emlf').write_text('module Sealed (count) where\ncount n = addInt n 40\n')
    package('export-checked-release', sealed, work / 'release-cache', work / 'release-build', 'release', release)
    # The consumer gets only the checked release. Its store has never seen the producer.
    (sealed.parent / 'Sealed.emlf').unlink()
    fresh = manifest('fresh', library={'modules': {'Fresh': 'Fresh.emlf'}})
    implementation = fresh.parent / 'Fresh.emlf'
    implementation.write_text('module Fresh (count) where\ncount n = addInt n 5\n')
    composed = manifest('composed', library={'modules': {'Composed': 'Composed.emlf'}}, dependencies={
        'fresh': {'path': '../fresh'},
        'sealed': {'release': '../checked-release', 'sha256': sha(release / 'release.json')}})
    (composed.parent / 'Composed.emlf').write_text(
        'module Composed (total) where\nimport qualified Fresh\nimport qualified Sealed\n'
        'total n = addInt (Fresh.count n) (Sealed.count 1)\n')
    dormant = manifest('dormant', library={'modules': {'Dormant': 'Dormant.emlf'}})
    (dormant.parent / 'Dormant.emlf').write_text('module Dormant (Ticket(..), count) where\n'
                                                'data Ticket = Ticket Int\ncount n = addInt n 100\n')
    app = manifest('consumer', executables={'mixed': {'main': 'Main.emlf'}}, dependencies={
        'fresh': {'path': '../fresh'}, 'composed': {'path': '../composed'},
        'dormant': {'path': '../dormant'}, 'sealed': {'release': '../checked-release', 'sha256': sha(release / 'release.json')}})
    (app.parent / 'Main.emlf').write_text('module Main where\nimport qualified Fresh\nimport qualified Composed\n'
                                         'import qualified Dormant\n'
                                         'measure :: (Dormant.Ticket -> Dormant.Ticket) -> Int -> Int\n'
                                         'measure witness number = number\n'
                                         'main = printInt (measure (\\x -> x) (addInt (Composed.total 2) (Fresh.count 0)))\n')
    fresh_id = 'fresh/0.1.0/library'
    composed_id = 'composed/0.1.0/library'
    sealed_id = 'sealed/0.1.0/library'

    def build(name, chosen, expected):
        report_path = package(name, app, shared, work / 'build', 'build')
        report = json.loads(report_path.read_text())
        # Keep the evidence for this build before the next invocation replaces the report.
        (runner.output / (name + '.build-report.json')).write_bytes(report_path.read_bytes())
        check(report['complete'], name + ' left an incomplete build')
        raw = (runner.output / (name + '.stderr')).read_bytes()
        decisions, _ = dependency_diagnostics(raw)
        recorded = report['dependency_modes']
        for row in recorded:
            check({k: row[k] for k in ('dependency', 'mode', 'reason')} in decisions,
                  name + ' did not print the recorded decision')
        required = {(fresh_id, chosen), (composed_id, 'native'),
                    (sealed_id, 'ir'), ('dormant/0.1.0/library', 'unused')}
        check(required <= {(row['dependency'], row['mode']) for row in recorded if row['stage'] == 'link'},
              name + ' selected the wrong artifact for a direct dependency')
        check(len(report['codegen']) == 1, name + ' did not emit exactly one executable')
        folder = Path(report['codegen'][0]['query_report']).parent
        inventory = json.loads((folder / 'native-dependencies.json').read_text())
        check(required <= {(r['dependency'], r['mode']) for r in inventory['dependency_modes']},
              name + ' emitted different dependency modes')
        objects = {r['dependency']: r for r in inventory['objects']}
        check(len(objects) == len(inventory['objects']), name + ' linked one provider more than once')
        check(set(objects) == ({fresh_id, composed_id} if chosen == 'native' else {composed_id}),
              name + ' linked an object for a checked dependency or omitted a selected object')
        for row in objects.values():
            check(sha(row['path']) == row['sha256'], name + ' linked different object bytes')
        runner.run(name + '-executable', [exe], expected=expected)
        return objects, recorded

    # Composed consumes native Fresh and checked-only Sealed; the root also
    # consumes Fresh directly. (2 + 5) + (1 + 40) + (0 + 5) = 53.
    cold, cold_modes = build('package-cold', 'native', b'53\n')
    check(any(row['dependency'] == fresh_id and row['mode'] == 'source' and row['stage'] == 'check'
              for row in cold_modes), 'cold package omitted its source dependency')
    warm, _ = build('package-warm', 'native', b'53\n')
    check(cold[fresh_id] == warm[fresh_id], 'warm package used a different native object')
    Path(cold[fresh_id]['path']).write_bytes(b'damaged object in the isolated consumer cache\n')
    build('package-checked-fallback', 'ir', b'53\n')
    implementation.write_text('module Fresh (count) where\ncount n = addInt n 6\n')
    changed, _ = build('package-edited', 'native', b'55\n')
    check(changed[fresh_id]['sha256'] != cold[fresh_id]['sha256'],
          'editing a library reused its obsolete native object')

    report = json.loads((work / 'build/build-report.json').read_text())
    check_pinned_link(runner, compiler, fresh_id, report, changed, expected=b'55\n')
    common = manifest('unified', executables={'unified': {'main': 'Main.emlf'}})
    (common.parent / 'Main.emlf').write_text(UNIFIED_SOURCE)
    package('unified-package', common, shared, work / 'unified-build', 'build')
    runner.run('unified-package-execute', [work / 'unified-build/bin/unified'], expected=b'42\n')


def check_pinned_link(runner, compiler, dep, package, linked, expected):
    """Replay the exported compiler handoff with the dependency body physically absent."""
    work = runner.root
    root = Path(next(row['metadata'] for row in package['crates'] if row['crate'].endswith('/target-mixed')))
    body = Path(next(row['metadata'] for row in package['crates'] if row['crate'] == dep)).with_suffix('.mlfco')
    folder = Path(package['codegen'][0]['query_report']).parent
    plan = json.loads((folder / 'native-plan.json').read_text())
    target = folder / 'native-target.json'
    candidate = next(row for row in plan['dependencies'] if row['crate_id'] == dep)
    checked = candidate.pop('checked')
    if Path(checked['path']) != body or sha(body) != checked['sha256'] or sha(target) != plan['target_sha256']:
        raise ValueError('pinned inputs differ from the checked crate and target')
    command = next(row['argv'] for row in package['commands']
                   if linked[dep]['path'] in row['argv'] and any(Path(arg).name == 'runtime.o' for arg in row['argv']))
    native_objects = {row['path'] for row in linked.values()}

    def emit(name, wanted=None):
        request = work / (name + '.plan.json')
        request.write_text(json.dumps(plan) + '\n')
        output = work / (name + '.report.json')
        result = runner.run(name, [compiler, '--crate-to-native-llvm', root,
                            '--native-dependencies', request, '--native-plan-sha256', sha(request),
                            '--native-target', target, '--native-report', output],
                            status=0 if wanted else 1, expected=None if wanted else b'')
        if wanted is None:
            if dep.encode() not in result.stderr or output.exists():
                raise ValueError(name + ' must reject the unimplemented dependency before emission')
            return
        observed = json.loads(output.read_text())
        modes = {row['dependency']: row['mode'] for row in observed['dependency_modes']}
        if modes.get(dep) != wanted or ((dep in observed['selected']) != (wanted == 'native')):
            raise ValueError(name + ' selected the wrong dependency implementation')
        llvm = work / (name + '.ll')
        llvm.write_bytes(result.stdout)
        binary = work / (name + '.bin')
        argv = []
        for arg in command[:command.index('-o')]:
            if Path(arg).name == 'program.o':
                argv.extend([llvm, *[row['path'] for row in observed['objects']]])
            elif arg not in native_objects:
                argv.append(arg)
        runner.run(name + '-link', [*argv, '-o', binary])
        runner.run(name + '-execute', [binary], expected=expected)

    saved = body.rename(work / 'withheld.mlfco')
    try:
        emit('pinned-object-only', 'native')
        candidate['object'] = {**candidate['object'], 'path': str(work / 'absent.o')}
        emit('pinned-without-implementation')
    finally:
        saved.rename(body)
    candidate['checked'] = checked
    emit('pinned-checked-fallback', 'ir')
