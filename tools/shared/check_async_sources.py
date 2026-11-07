#!/usr/bin/env python3
"""Active async source compatibility, not native/runtime parity qualification."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from test_direct import ROOT, CommandRunner, authenticate_build, sha
from test_guest_state_laws import capture_inputs, unchanged

DIRECTORIES = ('tests/async-task', 'tests/async-process', 'tests/async-package',
               'tests/fixtures/async-completion')
POSITIVES = ('tests/async-task/Main.emlf', 'tests/async-task/Processes.emlf',
             'tests/async-task/WaitGraph.emlf', 'tests/async-task/Guards.emlf',
             'tests/async-process/Main.emlf', 'tests/async-process/Panic.emlf',
             'tests/async-package/Main.emlf')

# Match the existing completion/process/task parity source-command budget.
# The first authenticated run passed Task Main but Processes timed out at 120s
# without diagnostics. Keep target checking smaller and the aggregate watchdog
# at 1800s; a timeout remains an incomplete result, never a skipped case.
SOURCE_COMPILE_SECONDS = 600
TARGET_CHECK_SECONDS = 120

COMPLETION_RUNTIME = {'bounds-cancellation', 'mixed-values', 'polymorphic-lazy',
                      'scope-queues', 'scope-reuse', 'timers'}
COMPLETION_NEGATIVE = {'alias-widen', 'forge-completion', 'forge-scope',
                       'forge-subscription', 'function-confusion',
                       'generalize-allocated', 'impredicative-overwrite',
                       'mixed-values', 'wrong-kind'}


def sources(root=ROOT):
    return sorted(p for d in DIRECTORIES for p in (root / d).rglob('*.emlf'))


def stale_names(text):
    # Ignore strings and comments, preserving tokens outside them. These active
    # fixtures do not declare intentional user ADTs named Unit/List/Pair/Monad.
    text = re.sub(r'"(?:\\.|[^"\\])*"|--[^\n]*', ' ', text)
    return re.findall(r'\b(?:Unit|List|Nil|Cons|Pair|Triple)\b|\bclass\s+Monad\b', text)


def check_static(root=ROOT):
    files = sources(root)
    if not files or any(not (root / p).is_file() for p in POSITIVES):
        raise ValueError('missing active async source inventory')
    for subdir, expected in [('runtime', COMPLETION_RUNTIME), ('negative', COMPLETION_NEGATIVE)]:
        actual = {p.stem for p in (root / DIRECTORIES[-1] / subdir).glob('*.emlf')}
        if actual != expected:
            raise ValueError('completion source inventory changed: ' + subdir)
    # A single colon in an expression can be parsed as list construction.
    # Keep this deliberate kind error in an unambiguous declaration signature:
    # Completion expects *, while the supplied IO has kind * -> *.
    wrong_kind = root / DIRECTORIES[-1] / 'negative/wrong-kind.emlf'
    if wrong_kind.read_text() != 'main :: Completion IO\nmain = panic "unused"\n':
        raise ValueError('wrong-kind fixture must retain its explicit invalid kind signature')
    for p in files:
        if stale_names(p.read_text()):
            raise ValueError('stale nominal async identity: ' + str(p))
    for name in ('tests/async-task/io-unit.type', 'tests/async-process/io-unit.type'):
        if (root / name).read_bytes() != b'IO ()\n':
            raise ValueError('stale checked IO type oracle: ' + name)
    script = (root / 'tests/fixtures/async-completion/check.sh').read_text()
    if "printf 'IO ()\\n'" not in script:
        raise ValueError('stale completion checked IO type oracle')
    return files


def completion_rejection_pattern(name):
    # Match the existing native parity rejection-phase requirements exactly.
    return (r'cannot redefine|primitive type' if name.startswith('forge-') else
            r'kind|arity' if name == 'wrong-kind' else
            r'^Inference: cannot raise a protected type variable' if name == 'generalize-allocated' else r'^Inference:')


def check_lookup_roots(root, files, cwd):
    """No fixture-directory alias may shadow a producer-authenticated module."""
    if cwd.is_symlink() or not cwd.is_dir() or any(cwd.iterdir()):
        raise ValueError('compiler cwd must remain an empty regular directory')
    manifest = json.loads((root / 'shared-sources.json').read_text())
    roots = {p.parent for p in files} | {
        root / 'libraries/mlf-foundation', root / 'libraries/mlf-async', cwd}
    for source in files:
        # All reviewed entries are Main, explicitly or implicitly. A different
        # module name would add a hierarchy root to the resolver search path.
        names = re.findall(r'^\s*module\s+([A-Z][\w.]*)\s', source.read_text(), re.M)
        if names not in ([], ['Main']):
            raise ValueError('unexpected async entry module/hierarchy: ' + str(source))
    for item in manifest['modules']:
        expected = (root / item['path']).absolute()
        stem = item['module'].replace('.', '/')
        for directory in roots:
            for suffix in ('.hs', '.emlf'):
                candidate = directory / (stem + suffix)
                if candidate.exists() or candidate.is_symlink():
                    if candidate.absolute() != expected or candidate.resolve(strict=True) != expected:
                        raise ValueError('async source lookup shadows authenticated module: ' + str(candidate))


def run(producer, output):
    files = check_static()
    producer = producer.resolve(strict=True)
    receipt = producer / 'receipt.json'
    output.mkdir(parents=True, exist_ok=False)
    record = dict(complete=False, scope='active-async-source-check',
                  native_execution=False, runtime_parity=False, commands=[])
    def save():
        (output / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    save()
    try:
        authenticate_build(receipt, producer / 'bin')
        fixed = [Path(__file__), ROOT / 'tools/shared/test_direct.py',
                 ROOT / 'tools/shared/test_guest_state_laws.py', ROOT / 'shared-sources.json',
                 ROOT / 'tests/async-task/io-unit.type', ROOT / 'tests/async-process/io-unit.type',
                 ROOT / 'tests/fixtures/async-completion/check.sh']
        inputs = capture_inputs(ROOT, fixed)
        cwd = output / 'empty-cwd'
        cwd.mkdir()
        check_lookup_roots(ROOT, files, cwd)
        producer_hash = sha(receipt)
        record.update(inputs=inputs, producer_receipt_sha256=producer_hash)
        def integrity():
            unchanged(inputs, capture_inputs(ROOT, fixed))
            check_lookup_roots(ROOT, files, cwd)
            if sha(receipt) != producer_hash:
                raise ValueError('producer receipt changed during async source check')
        runner = CommandRunner(cwd, output, record, save)
        def command(*args, **kwargs):
            integrity()
            result = runner.run(*args, **kwargs)
            integrity()
            return result
        compiler = producer / 'bin/emlf'
        includes = ['-i', ROOT / 'libraries/mlf-foundation', '-i', ROOT / 'libraries/mlf-async']
        positives = [ROOT / p for p in POSITIVES] + sorted((ROOT / DIRECTORIES[-1] / 'runtime').glob('*.emlf'))
        for i, source in enumerate(positives):
            name = 'positive-' + str(i)
            command(name, [compiler, *includes, source], timeout=SOURCE_COMPILE_SECONDS)
            command(name + '-check', [compiler, '--check', output / (name + '.stdout')], expected=b'IO ()\n', timeout=TARGET_CHECK_SECONDS)
        # Retain intended negative phase, including protected-variable rejection.
        for source in sorted((ROOT / DIRECTORIES[-1] / 'negative').glob('*.emlf')):
            name = source.stem
            result = command('negative-' + name, [compiler, *includes, source], status=1, expected=b'', timeout=SOURCE_COMPILE_SECONDS)
            pattern = completion_rejection_pattern(name)
            if not re.search(pattern.encode(), result.stderr):
                raise ValueError('wrong rejection phase: ' + name)
        authenticate_build(receipt, producer / 'bin')
        integrity()
        record.update(complete=True, positives=len(positives), completion_negatives=len(COMPLETION_NEGATIVE))
    except BaseException as error:
        record['error'] = str(error)
        raise
    finally:
        save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.producer is None:
        check_static()
        print('Active async static identity checks passed (not source or runtime qualification).')
    else:
        if args.output is None:
            parser.error('--output required with --producer')
        run(args.producer, args.output.resolve())
