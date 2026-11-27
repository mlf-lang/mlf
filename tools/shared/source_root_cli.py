"""Exercise the public compiler against independent types, effects and cache expectations."""
import hashlib
import json

from artifact_binary_reference import read_document
from artifact_binary_typed import unpack
from query_generation import Generation, digest


def require(condition, message):
    if not condition:
        raise ValueError(message)


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

    runner.run('expr-run', [*argv, '--run', '--expr', source], overrides=no_storage, expected=b'42\n')
    runner.run('stdin-type', [*argv, '--type'], stdin=source.encode(), overrides=no_storage, expected=b'IO ()\n')
    runner.run('stdin-run', [*argv, '--run', '-'], stdin=source.encode(), overrides=no_storage, expected=b'42\n')
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
    runner.run('check-target', [compiler, '--check', target], expected=b'IO ()\n')
    runner.run('run-target', [compiler, '--run-xmlf', target], expected=b'42\n')
    cold = published_queries(cache)
    require(cold and any(cache.rglob('*.mlfqr')), 'file root did not publish checked queries')
    file_run('file-warm', ['--run', entry], expected=b'42\n')
    require(published_queries(cache) == cold, 'warm file produced a different query generation')

    odd.write_text(odd_source.replace('then false', 'then true'))
    file_run('dependency-changed', ['--run', entry], expected=b'7\n')
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


def check_installed_root(runner, compiler):
    work = runner.root
    entry = work / 'NativeMain.emlf'
    # Bootstrap.Std.length crosses the installed object boundary. A local-only
    # program could return the same value after entirely bypassing that object.
    entry.write_text('import qualified Bootstrap.Std as S\n'
                     'main = printInt (S.length ((:) 3 ((:) 4 [])))\n')
    executable = work / 'native-main'
    receipt = work / 'native-build/receipt.json'
    runner.run('build-installed-file', [compiler, entry, '-o', executable, '--build-dir', 'native-build'],
               overrides={'MLF_SOURCE_CACHE_DIR': ''}, expected=(str(receipt) + '\n').encode())
    runner.run('execute-installed-file', [executable], expected=b'2\n')
    report = json.loads(receipt.read_text())
    require(report.get('complete') and report.get('fixed_library_reused')
            and report.get('native_export_count', 0) > 0 and report.get('stdlib_path') == 'installed',
            'executable did not use checked exports from the installed library')
    require(published_queries(work / '.mlf-build/cache/source-roots'),
            'executable preparation skipped file-root query publication')
    require(not list(work.rglob('*.mlfci')) and not list(work.rglob('*.mlfco')),
            'direct executable compilation published package crate artifacts')

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
