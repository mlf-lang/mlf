"""Exercise the public compiler against independent types, effects and cache expectations."""
import hashlib
import json
import re

from artifact_binary_reference import read_document
from artifact_binary_typed import unpack
from query_generation import Generation, digest
from test_direct import dependency_diagnostics, sha


def require(condition, message):
    if not condition:
        raise ValueError(message)


def modes(runner, name):
    raw = (runner.output / (name + '.stderr')).read_bytes()
    decisions, diagnostics = dependency_diagnostics(raw)
    require(decisions and not diagnostics, name + ' must write only dependency decisions to stderr')
    return decisions


def require_source(runner, name, *dependencies):
    rows = modes(runner, name)
    sources = {row['dependency'] for row in rows if row['mode'] == 'source'}
    require(set(dependencies) <= sources and any(row['reason'] == 'root input' for row in rows),
            name + ' omitted the source input or a compiled dependency')
    return rows


def published_queries(cache):
    return {path.relative_to(cache): path.read_bytes() for path in cache.rglob('CURRENT')}


def headerless_inference(cache):
    pointers = list(cache.rglob('CURRENT'))
    require(len(pointers) == 1, 'headerless file should have one published root')
    directory = pointers[0].parent
    current = digest(read_document(pointers[0].read_bytes(), 6).values()[0])
    raw = (directory / 'generations' / (current + '.mlfqg')).read_bytes()
    generation = Generation(raw, expected_hash=current)
    result = {}
    for key, node in generation.nodes.items():
        kind, identity = unpack(key)
        if kind != 'InferScc':
            continue
        members = unpack(identity)
        for binding in ('quietcell', 'loudcell'):
            if any(binding in name for name in members):
                require(len(members) == 1 and binding not in result,
                        binding + ' must own a distinct inference group')
                address = node['payload']
                require(address, binding + ' has no durable checked query')
                payload = (directory / 'results' / (address + '.mlfqr')).read_bytes()
                require(hashlib.sha256(payload).hexdigest() == address, binding + ' query address mismatch')
                result[binding] = address
    require(set(result) == {'quietcell', 'loudcell'}, 'headerless declarations collapsed into one entry query')
    return result


def check_headerless_groups(runner, compiler):
    work = runner.root
    entry = work / 'Headerless.emlf'
    body = ('quietcell n = addInt n 40\n'
            'loudcell n = addInt n 1\n'
            'main = printInt (quietcell (loudcell 1))\n')
    entry.write_text(body)
    cache = work / 'headerless-cache'
    env = {'MLF_SOURCE_CACHE_DIR': str(cache)}
    argv = [compiler, '--no-prelude', '--run', entry]
    runner.run('headerless-cold', argv, overrides=env, expected=b'42\n')
    before = headerless_inference(cache)
    # The publication failpoint fires only when a new generation must be written.
    runner.run('headerless-warm', argv, overrides={**env, 'MLF_QUERY_FAILPOINT': 'before-index'},
               expected=b'42\n')
    entry.write_text(body.replace('addInt n 1', 'addInt n 2'))
    runner.run('headerless-edit', argv, overrides=env, expected=b'43\n')
    after = headerless_inference(cache)
    require(after['quietcell'] == before['quietcell'] and after['loudcell'] != before['loudcell'],
            'headerless edit must retain the independent query and replace the changed one')


def check_script_instances(runner, compiler):
    # The final expression must solve its imported and local dictionaries as
    # a use site, after each real source declaration has been generalized.
    body = 'do { value <- pure 41; printInt (addInt value 1) }'
    runner.run('script-instance-expr-type', [compiler, '--type', '--expr', body],
               expected=b'IO ()\n')
    runner.run('script-instance-expr-run', [compiler, '--run', '--expr', body],
               expected=b'42\n')
    runner.run('script-instance-stdin-run', [compiler, '--run', '-'],
               stdin=body.encode(), expected=b'42\n')
    own_class = ('class Bump a where { bump :: a -> Int }\n'
                 'instance Bump Int where { bump value = addInt (helper value) 1 }\n'
                 'helper value = value\n'
                 'main = printInt (bump 41)\n')
    runner.run('script-instance-own-expr', [compiler, '--run', '--expr', own_class],
               expected=b'42\n')
    runner.run('script-instance-own-no-prelude',
               [compiler, '--no-prelude', '--run', '--expr', own_class], expected=b'42\n')
    runner.run('script-instance-own-stdin', [compiler, '--run', '-'],
               stdin=own_class.encode(), expected=b'42\n')
    runner.run('script-instance-local-eq', [compiler, '--run', '--expr',
               'data Box = Box Int\n'
               'instance Eq Box where { (==) (Box a) (Box b) = eqInt a b }\n'
               'main = printInt (if Box 1 == Box 1 then 42 else 0)\n'], expected=b'42\n')
    cache = runner.root / 'script-instance-cache'
    for label, text in (('imported', 'main = ' + body + '\n'), ('own', own_class)):
        entry = runner.root / ('ScriptInstances-' + label + '.emlf')
        entry.write_text(text)
        argv = [compiler, '--run', entry]
        runner.run('script-instance-file-' + label + '-cold', argv,
                   overrides={'MLF_SOURCE_CACHE_DIR': str(cache)}, expected=b'42\n')
        runner.run('script-instance-file-' + label + '-warm', argv,
                   overrides={'MLF_SOURCE_CACHE_DIR': str(cache), 'MLF_QUERY_FAILPOINT': 'before-index'},
                   expected=b'42\n')
        if label == 'own':
            entry.write_text(text.replace('addInt (helper value) 1', 'addInt (helper value) 2'))
            runner.run('script-instance-file-own-edited', argv,
                       overrides={'MLF_SOURCE_CACHE_DIR': str(cache)}, expected=b'43\n')

    # The entry boundary must enclose the complete final expression. Hoisting
    # either of its local lets would merge distinct lexical identities.
    runner.run('script-nested-shadow-type', [compiler, '--no-prelude', '--type', '--expr',
               'let value = 1 in let value = true in value'], expected=b'Bool\n')
    for label, text in (
        ('nested-shadow', 'let value = 1 in let value = true in printInt (if value then 42 else 0)'),
        ('declaration-shadow', 'value = 1\nlet value = true in printInt (if value then 42 else 0)'),
        ('local-polymorphism', 'let identity = \\value -> value in '
         'printInt (if identity true then identity 42 else 0)'),
        ('unused-let', 'let unused = panic "not demanded" in printInt 42'),
        ('signed-use', 'same :: forall a. Eq a => a -> Bool\nsame value = value == value\n'
         'main = printInt (if same 1 then 42 else 0)\n'),
    ):
        runner.run('script-' + label, [compiler, '--run', '--expr', text], expected=b'42\n')

    qualified = runner.run('script-qualified-type', [compiler, '--type', '--expr',
        'class Bump a where { bump :: a -> Int }\n'
        '(\\value -> bump value) :: forall a. Bump a => a -> Int'])
    require(re.fullmatch(rb'forall (\w+)\. Bump \1 => \1 -> Int\n', qualified.stdout),
            'script entry lost its explicitly qualified source type')
    missing = runner.run('script-missing-instance', [compiler, '--no-prelude', '--run', '--expr',
        'class Bump a where { bump :: a -> Int }\nmain = printInt (bump 41)\n'], status=1, expected=b'')
    require(missing.stderr.startswith(b'Resolution:') and b'Bump Int' in missing.stderr,
            'script entry did not reject the missing local instance during resolution')
    no_prelude = runner.run('script-no-prelude', [compiler, '--no-prelude', '--run', '--expr', body],
                            status=1, expected=b'')
    require(no_prelude.stderr.startswith(b'ModuleResolution:'),
            'script instance recovery silently introduced an implicit Prelude')


def check_source_root(runner, compiler):
    work = runner.root
    modules = work / 'modules'
    modules.mkdir()
    # The import cycle contains a mutually recursive pair and a separately
    # generalized identity used at Int and Bool in the same root.
    (modules / 'Even.emlf').write_text(
        'module Even (even, identity) where\nimport qualified Odd\n'
        'even n = if n == 0 then true else Odd.odd (n-1)\nidentity x = x\n')
    odd = modules / 'Odd.emlf'
    odd_source = ('module Odd (odd) where\nimport qualified Even\n'
                  'odd n = if n == 0 then false else Even.even (n-1)\n')
    odd.write_text(odd_source)
    source = ('import qualified Even\nmain = printInt (if Even.identity (Even.even 3) '
              'then 7 else Even.identity 42)\n')
    entry = work / 'Main.emlf'
    entry.write_text(source)
    argv = [compiler, '-i', modules]
    cache = work / 'selected source cache'

    def file_run(name, args, **expectations):
        return runner.run(name, [*argv, *args], overrides={'MLF_SOURCE_CACHE_DIR': str(cache)}, **expectations)

    unusable = work / 'regular-file'
    unusable.write_text('not a cache directory\n')
    no_storage = {'MLF_SOURCE_CACHE_DIR': str(unusable)}

    runner.run('literal-type', [compiler, '--no-prelude', '--type', '--expr', '5'],
               overrides=no_storage, expected=b'Int\n')
    literal = require_source(runner, 'literal-type')
    require(len(literal) == 1, 'a primitive expression should report its single source root')
    runner.run('expr-run', [*argv, '--run', '--expr', source], overrides=no_storage, expected=b'42\n')
    runner.run('stdin-type', [*argv, '--type'], stdin=source.encode(), overrides=no_storage, expected=b'IO ()\n')
    runner.run('stdin-run', [*argv, '--run', '-'], stdin=source.encode(), overrides=no_storage, expected=b'42\n')
    for name in ('expr-run', 'stdin-type', 'stdin-run'):
        require_source(runner, name, 'Even', 'Odd')
    default_build = work / '.mlf-build'
    require(not default_build.exists(), 'expression or stdin created a default cache')
    # An inaccessible implicit cache must still allow checking a read-only project.
    # A regular file in the way gives the same failure even for privileged CI users.
    default_build.write_text('not a directory\n')
    runner.run('uncachable-default', [*argv, '--type', entry],
               overrides={'MLF_SOURCE_CACHE_DIR': ''}, expected=b'IO ()\n')
    file_error = runner.run('unusable-file-cache', [*argv, '--type', entry],
                            overrides=no_storage, status=1, expected=b'')
    require(file_error.stderr, 'explicit unusable file cache was silently ignored')

    target = work / 'root.xmlf'
    target.write_bytes(file_run('file-target', [entry]).stdout)
    require_source(runner, 'file-target', 'Even', 'Odd')
    runner.run('check-target', [compiler, '--check', target], expected=b'IO ()\n')
    runner.run('run-target', [compiler, '--run-xmlf', target], expected=b'42\n')
    llvm = file_run('file-llvm', ['--emit-llvm', entry]).stdout
    require_source(runner, 'file-llvm', 'Even', 'Odd')
    require(b'define i32 @main(' in llvm and b'dependency ' not in llvm, 'expected standalone LLVM on stdout')
    file_run('file-llvm-warm', ['--emit-llvm-gc', entry], expected=llvm)
    require_source(runner, 'file-llvm-warm', 'Even', 'Odd')
    cold = published_queries(cache)
    require(cold and any(cache.rglob('*.mlfqr')), 'file root did not publish checked queries')
    file_run('file-warm', ['--run', entry], expected=b'42\n')
    require(published_queries(cache) == cold, 'warm file produced a different query generation')

    odd.write_text(odd_source.replace('then false', 'then true'))
    file_run('dependency-changed', ['--run', entry], expected=b'7\n')
    require(file_run('dependency-changed-llvm', ['--emit-llvm', entry]).stdout != llvm,
            'editing an imported function reused obsolete LLVM')
    changed = published_queries(cache)
    require(changed != cold, 'editing an imported definition reused the old generation')

    for label, text, phase in (
        ('infer', 'main = putStrLn 1\n', b'Inference:'),
        ('resolve', 'import MissingRootModule\nmain = printInt 1\n', b'ModuleResolution:'),
        ('parse', 'main = (\n', b'Parsing:'),
    ):
        entry.write_text(text)
        error = file_run('rejected-' + label, ['--run', entry], status=1, expected=b'')
        require(error.stderr.startswith(phase), label + ' reported the wrong compilation phase')
        require(published_queries(cache) == changed, label + ' published a failed file root')
    entry.write_text(source)
    odd.write_text(odd_source)
    file_run('restored-run', ['--run', entry], expected=b'42\n')
    check_headerless_groups(runner, compiler)
    check_script_instances(runner, compiler)


def check_installed_root(runner, compiler):
    work = runner.root
    entry = work / 'NativeMain.emlf'
    # Bootstrap.Std.length crosses the installed object boundary. A local-only
    # program could return the same value after entirely bypassing that object.
    (work / 'Local.emlf').write_text('module Local (items) where\nitems = (:) 3 ((:) 4 [])\n')
    entry.write_text('module Main where\nimport qualified Bootstrap.Std as S\nimport qualified Local\n'
                     'main = printInt (S.length Local.items)\n')
    executable = work / 'native-main'
    receipt = work / 'native-build/receipt.json'
    installation = json.loads(runner.run('installed-info', [compiler, '--native-install-info']).stdout)
    argv = [compiler, '-i', work]
    includes = [arg for path in installation['source_roots'] for arg in ('-i', path)]
    checked = runner.run('installed-standalone-llvm', [*argv, *includes, '--emit-llvm', entry]).stdout
    checked_rows = require_source(runner, 'installed-standalone-llvm', 'Main', 'Local')
    require(b'define i32 @main(' in checked and b'dependency ' not in checked,
            'standalone LLVM includes invalid text or has no entry')
    runner.run('build-installed-file', [*argv, entry, '-o', executable, '--build-dir', 'native-build'],
               overrides={'MLF_SOURCE_CACHE_DIR': ''}, expected=(str(receipt) + '\n').encode())
    runner.run('execute-installed-file', [executable], expected=b'2\n')
    report = json.loads(receipt.read_text())
    selected = require_source(runner, 'build-installed-file', 'Main', 'Local')
    require(selected == report.get('dependency_modes'), 'stderr disagrees with the executable receipt')
    runner.run('installed-native-llvm', [*argv, '--emit-native-llvm', entry],
               expected=(receipt.parent / 'program.ll').read_bytes())
    emitted = require_source(runner, 'installed-native-llvm', 'Main', 'Local')
    require(emitted == [row for row in selected if row['dependency'] != 'runtime'],
            'native LLVM and executable compilation selected different dependencies')
    owners = {row['dependency'] for row in selected if row['mode'] == 'native' and row['dependency'] != 'runtime'}
    require(owners and owners <= {row['dependency'] for row in checked_rows if row['mode'] == 'ir'},
            'standalone IR and native linking did not consume the same installed dependencies')
    linked = report['link_objects']
    link = next(row for row in report['commands'] if row['phase'] == 'link')['command']
    require(len(linked) >= 2 and all(row['path'] in link and sha(row['path']) == row['sha256'] for row in linked),
            'link did not receive both the recorded native library object and runtime')
    require(report.get('complete') and report.get('fixed_library_reused')
            and report.get('native_export_count', 0) > 0 and report.get('stdlib_path') == 'installed',
            'executable did not use checked exports from the installed library')
    require(published_queries(work / '.mlf-build/cache/source-roots'),
            'executable preparation skipped file-root query publication')
    require(not list(work.rglob('*.mlfci')) and not list(work.rglob('*.mlfco')),
            'direct executable compilation published package crate artifacts')

    # An explicit local module with the same public name has different semantics.
    override = work / 'override'
    (override / 'Bootstrap').mkdir(parents=True)
    (override / 'Bootstrap/Std.emlf').write_text('module Bootstrap.Std (length) where\nlength xs = 19\n')
    shadow_exe = work / 'shadowed-main'
    shadow_receipt = work / 'shadow-build/receipt.json'
    runner.run('build-shadowed-source', [compiler, '-i', override, '-i', work, entry, '-o', shadow_exe,
                                        '--build-dir', 'shadow-build'],
               expected=(str(shadow_receipt) + '\n').encode())
    shadow = json.loads(shadow_receipt.read_text())
    shadow_rows = require_source(runner, 'build-shadowed-source', 'Main', 'Local', 'Bootstrap.Std')
    require(shadow_rows == shadow['dependency_modes'] and not shadow['fixed_library_reused']
            and len(shadow['link_objects']) == 1 and shadow['link_objects'][0] in linked,
            'the shadowed standard-library object still entered the native link')
    runner.run('execute-shadowed-source', [shadow_exe], expected=b'19\n')

    # Missing imported sources attempt the ordinary fallback and keep their
    # module-resolution diagnostic. Malformed source fails before admission.
    for label, source, phases in (
        ('native-missing-import', 'import MissingInstalledModule\nmain = 1\n',
         (b'native library fallback: ModuleResolution:', b'ModuleResolution:')),
        ('native-parse-error', 'main = (\n', (b'Parsing:',)),
    ):
        result = runner.run(label, [compiler, '--emit-native-llvm', '--expr', source],
                            status=1, expected=b'')
        diagnostics = result.stderr.splitlines()
        require(diagnostics and diagnostics[0].startswith(phases[0]), label + ': wrong initial diagnostic')
        if len(phases) == 2:
            require(any(line.startswith(phases[1]) for line in diagnostics[1:]),
                    label + ': fallback lost the module-resolution error')
