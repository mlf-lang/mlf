#!/usr/bin/python3
"""Fresh ordinary VALIDATE -> BENCH. No native generation or fixed-point run."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time
import types

HERE = Path(__file__).resolve().parent
N = HERE.parent
R = N.parent
I = R / 'recovery/tools/performance/full-compiler/continuation-20261111/sparse-attribution-r13'
COMMITS = {'A': 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1',
           'B': '8433ca438213516118ce9079adf9db0cb91188bc'}
ROOTS = {'A': R, 'B': N}
BUDGETS = {'VALIDATE': 600, 'BENCH': 600}
SEQUENCE = list('ABBA' * 3)
FIXTURE = R / 'encode-edit/fixtures/EncodeInputReuse.hs'
FIRST_FAILURE = R / 'encode-edit/fixtures/EncodeFirstFailure.hs'
FIRST_FAILURE_EXPECTED = R / 'encode-edit/fixtures/EncodeFirstFailure.expected'
FIRST_FAILURE_OUTPUT = b'PASS\tfirst-encoding-left-before-poison\nPASS\tfinite-success-exact-session-and-bytes\nSUMMARY\t2\t2\n'
INITIAL_FIXTURE_SHA = 'a379a3b2313c0c52affcfed0bd6144f0962f4201b5e89b6d7f0caa2e43db3e95'
FIXTURE_RELATIVES = {'query-index': 'tools/shared/fixtures/item4/QueryIndex.hs',
                    'artifact-binary': 'tools/shared/fixtures/item4/ArtifactBinary.hs'}
TOOL_PINS = {
    'guard.py': '53a5b322fe8ed9e1a527dda0596215ffc81322b43b1864442827c9056c313d0e',
    'oracles.py': '9a9bc72aef6bfe7cf3853620b8b4dc055b12d5ab50df1f53dd95247775d8777f',
    'stats.py': 'b558556b11af12b117444f6476c5e841fa1b4beddc8f7cfe5e13047f2426a84c',
    'insertion-map.json': 'c6b7882730f55fb6b8239c6e6462de22eff97e13696018e8133ce1f7d547bcc6',
    'foundation14-source.json': 'e85b2776812a28fafd4074b5c4823f26a76ad2e0137492964ade76450f68d7fa',
}
ADAPTER_PINS = {'A': 'c6b750e79f587f3f28e20037891e78e8c9ef69f111487b60d6721fce4772afe0',
                'B': '3fbecfbf6ce69568ac19a506b7061c419c214d3f9c9a136ccc24d8e7d781b8a8'}
ALLOWED_ENV = {'HOME', 'PATH', 'LD_LIBRARY_PATH', 'LC_ALL', 'LANG', 'TZ',
    'GHC_ENVIRONMENT', 'GHCRTS', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
    'MAKEFLAGS', 'PYTHONDONTWRITEBYTECODE', 'TMPDIR', 'CC', 'TC',
    'LIBRARY_PATH', 'PKG_CONFIG_PATH'}
FORBIDDEN_ENV = {'MLF_QUERY_PROFILE', 'MLF_QUERY_SEMANTIC_AUDIT', 'MLF_QUERY_FAILPOINT',
    'LD_PRELOAD', 'LD_AUDIT', 'LD_DEBUG', 'LD_DEBUG_OUTPUT', 'LD_PROFILE',
    'LD_ASSUME_KERNEL', 'GLIBC_TUNABLES', 'GHC_PACKAGE_PATH', 'GHC_CHARENC', 'HPCTIXFILE'}
CASES = [
    ('version', ['--version'], 0, b'emlf 0.3.0\n', b''),
    ('identity', ['--implementation-identity'], 0, b'MLF/shared-haskell-v1 GHC\n', b''),
    ('semantic-42', ['--run', '--expr', 'printInt (40 + 2)'], 0, b'42\n', b''),
    ('unicode-positive', ['--run', '--expr', 'putStrLn "λ雪🙂"'], 0, 'λ雪🙂\n'.encode(), b''),
    ('type-rejection', ['--type', '--expr', '(True :: Int)'], 1, b'',
     b'Inference: type constructor mismatch: Con "Bool" [] versus Con "Int" []\n'),
]
PURE_IDS = ['empty', 'singleton-binding', 'contracts-kinds-classes-protection-and-shared-values',
    'datatypes-unicode-and-higher-kinds', 'mixed-ordered-batch', 'same-key-ordered-replacement',
    'old-matching-nodes', 'old-authority-changed', 'already-active-entries',
    'old-row-fields-not-hash-only', 'dependency-unchanged', 'dependency-changed',
    'dependency-deleted', 'partial-contract-first-before-later-fields',
    'partial-declaration-first-before-tail', 'value-before-session',
    'successful-value-then-session', 'empty-does-not-force-scope']
PUBLICATION_IDS = ['publication-cold', 'publication-warm', 'publication-changed', 'publication-deleted']
REFERENCE = R / 'profile-r14-01/stages/TARGET-QUALIFICATION/ordinary-Q/unit'
BUILTIN = R / 'profile-r14-01/builtin/builtin'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def initialise():
    """Load only the fixed, hash-pinned original tools; never run at import."""
    global O, G, STATS
    for name, expected in TOOL_PINS.items():
        p = I / name
        require(all(not q.is_symlink() for q in [p, *p.parents]), 'tool symlink')
        require(hashlib.sha256(p.read_bytes()).hexdigest() == expected, 'original tool changed: ' + name)
    def module(path, name):
        value = types.ModuleType(name)
        value.__file__ = str(path)
        exec(compile(path.read_bytes(), str(path), 'exec'), value.__dict__)
        return value
    O = module(I / 'oracles.py', 'r15_common_oracles')
    G = module(I / 'guard.py', 'r15_original_guard')
    STATS = module(I / 'stats.py', 'r15_original_stats')


def code_pins():
    paths = [HERE / 'controller.py', *[I / name for name in TOOL_PINS]]
    paths += [root / 'ordinary/controller.py' for root in ROOTS.values()]
    return {str(p): O.sha(p) for p in paths}


def work_path(value):
    p = O.safe(value)
    require(p.parent == N and re.fullmatch(r'validation-run[0-9]{2,}', p.name),
            'work must be N/validation-runNN, never an old work root')
    return p


def phase_paths(work, phase):
    return work / 'stages' / phase, work / 'guards' / phase


def worker_command(phase, path, digest):
    return [str(Path(sys.executable).resolve()), '-B', str(HERE / 'controller.py'),
            '_worker', phase, '--admission', str(path), '--sha256', digest]


def claim(phase, path):
    return {'phase': phase, 'admission': O.pin(path), 'retry_allowed': False}


def expected_fixture_pins():
    paths = [FIXTURE, FIRST_FAILURE, FIRST_FAILURE_EXPECTED]
    for root in ROOTS.values():
        paths += [root / 'source' / rel for rel in FIXTURE_RELATIVES.values()]
    return {str(p): O.sha(p) for p in paths}


def reference_pins():
    paths = [R / ('profile-r14-01/stages/' + p + '/receipt.json') for p in ('QUALIFY', 'TARGET-QUALIFICATION')]
    paths += [R / ('profile-r14-01/guards/' + p + '/guard.json') for p in ('QUALIFY', 'TARGET-QUALIFICATION')]
    paths += [Path(str(BUILTIN) + x) for x in O.SUFFIXES[:2]]
    paths += [Path(str(REFERENCE) + x) for x in O.SUFFIXES]
    return {str(p): O.sha(p) for p in paths}


def clean_outer(row, *, argv=None, cwd=None, output=None, bound=None, epoch=None,
                locks=None, seconds=None):
    require(row['schema'] == 'sparse-scc-guard-v1' and row['complete'] is True
            and row['exit_code'] == 0 and row['reason'] is None
            and row['cleanup'] is True and row['lock_reacquired'] is True
            and row.get('lease_cleared') is True and row['test_only'] is False
            and row['standalone_admission'] is True and row['limits'] == G.LIMITS,
            'successful final outer cleanup required')
    for key, value in {'command': argv, 'cwd': str(cwd) if cwd else None,
            'output': str(output) if output else None, 'bounded_root': str(bound) if bound else None,
            'epoch': epoch, 'locks': locks, 'seconds': seconds}.items():
        if value is not None:
            require(row[key] == value, 'outer binding mismatch: ' + key)


def validate_admission(path, digest, phase):
    require(phase in BUDGETS and O.sha(path) == digest, 'phase/admission SHA mismatch')
    a = O.load(path)
    require(a['schema'] == 'r15-ordinary-validation-admission-v1'
            and a['approved'] is True and a['phase'] == phase, 'fresh separate approved admission required')
    work = work_path(a['work'])
    require(a['budget_seconds'] == 600 and a['per_compile_seconds'] == 180
            and a['sequence'] == SEQUENCE and a['commits'] == COMMITS
            and a['native_fixed_point_ab'] is False, 'fixed ordinary protocol required')
    require(a['code_pins'] == code_pins(), 'runner/tools changed after review')
    for role, expected in ADAPTER_PINS.items():
        require(a['code_pins'][str(ROOTS[role] / 'ordinary/controller.py')] == expected, 'ordinary adapter changed')
    review = O.load(O.verify_pin(a['review']))
    require(review['complete'] is True and review['code_pins'] == a['code_pins']
            and review['fixture_pins'] == a['fixture_pins'], 'review must bind code and fixture bytes')
    require(a['fixture_pins'] == expected_fixture_pins(), 'fixture inventory/bytes changed')
    require(a['reference_pins'] == reference_pins(), 'r14 reference bytes changed')
    require(O.verify_pin(a['python']) == Path(sys.executable).resolve()
            == Path('/usr/bin/python3').resolve(), 'pinned /usr/bin/python3 required')
    require(set(a['ordinary']) == {'A', 'B'}, 'both ordinary handoffs required')
    for role, root in ROOTS.items():
        require(O.verify_pin(a['ordinary'][role]) == root / 'ordinary/ordinary-handoff.json', 'wrong ordinary handoff')
    require(O.verify_pin(a['epoch']) == N / 'coordination/lock-epoch.json', 'wrong candidate epoch')
    epoch = O.load(a['epoch']['path'])
    require(epoch['schema'] == 'astra-lock-epoch-v1' and epoch['new_epoch'] is True
            and epoch['historical_continuity_claimed'] is False
            and epoch['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and epoch['workspace'] == str(R), 'current fresh epoch required')
    require(a['locks'] == [epoch['shared'], epoch['reproduction']]
            and a['locks'][0]['path'] == str(R / '.astra-resource-locks/heavy.lock')
            and a['locks'][1]['path'] == str(N / 'source/.mlf-build/.reproduction.lock')
            and epoch['shared_peer_contention_passed'] is True
            and epoch['reproduction_reacquired'] is True, 'original two-lock admission required')
    O.absent(work / 'quarantine.json')
    O.absent(G.epoch_quarantine_path(a['locks'], a['epoch']))
    env = a['environment']
    require(set(env).issubset(ALLOWED_ENV)
            and all(type(k) is str and type(v) is str for k, v in env.items()), 'explicit environment strings required')
    require(not (FORBIDDEN_ENV & (set(os.environ) | set(env))), 'query/loader instrumentation forbidden')
    for role in ROOTS:
        original = O.load(O.verify_pin(O.load(a['ordinary'][role]['path'])['environment']))
        original['TMPDIR'] = str(work / 'tmp')
        require(env == original, 'environment differs from ordinary producer beyond bounded TMPDIR')
    require(env['GHCRTS'] == '' and env['GHC_ENVIRONMENT'] == '-'
            and env['LC_ALL'] == 'C.UTF-8' and env['PYTHONDONTWRITEBYTECODE'] == '1',
            'no RTS/environment overrides')
    require(a['prior'] == {} if phase == 'VALIDATE' else set(a['prior']) == {'receipt', 'outer', 'final'},
            'exact prior-stage inventory required')
    if phase == 'BENCH':
        folder, outer_dir = phase_paths(work, 'VALIDATE')
        for key, expected in {'receipt': folder / 'receipt.json', 'outer': outer_dir / 'guard.json',
                              'final': folder / 'final.json'}.items():
            require(O.verify_pin(a['prior'][key]) == expected, 'prior stage path mismatch')
        prior, final = O.load(a['prior']['receipt']['path']), O.load(a['prior']['final']['path'])
        require(prior['complete'] is True and prior['phase'] == 'VALIDATE'
                and final['complete'] is True and final['phase'] == 'VALIDATE'
                and final['worker_receipt'] == a['prior']['receipt']
                and final['outer'] == a['prior']['outer'], 'VALIDATE not finally complete')
        for key in ('work', 'code_pins', 'fixture_pins', 'reference_pins', 'ordinary', 'environment', 'epoch', 'locks'):
            require(prior[key] == a[key], 'VALIDATE binding changed: ' + key)
        clean_outer(O.load(a['prior']['outer']['path']), argv=prior['worker_command'],
                    cwd=HERE, output=outer_dir, bound=work, epoch=a['epoch'],
                    locks=a['locks'], seconds=600)
        O.check_pins(prior['input_pins'])
        O.check_pins(prior['output_pins'])
    return a, work


def verify_side(role, binding):
    root = ROOTS[role]
    source, ordinary = root / 'source', root / 'ordinary'
    producer = ordinary / 'build/producer'
    oracle = O.module(I / 'oracles.py', TOOL_PINS['oracles.py'])
    oracle.BASE = COMMITS[role]
    handoff = O.load(O.verify_pin(binding))
    require(handoff['producer'] == str(producer), 'wrong producer root')
    paths = {'receipt': producer / 'receipt.json', 'build_controller': ordinary / 'build/controller.json',
             'build_outer': ordinary / 'build/outer/guard.json',
             'controls': ordinary / 'controls/focused-control-receipt.json',
             'controls_controller': ordinary / 'controls/controller.json',
             'controls_outer': ordinary / 'controls/outer/guard.json',
             'relink': ordinary / 'relink-inputs.json'}
    for key, expected in paths.items():
        require(O.verify_pin(handoff[key]) == expected, 'wrong ordinary evidence path: ' + key)
    auth = oracle.authenticate(producer, source)
    require(len(auth['object_inputs']) == 284, 'full original 284 objects/interfaces required')
    controllers = {}
    for phase in ('BUILD', 'CONTROLS'):
        label = 'build' if phase == 'BUILD' else 'controls'
        rec = O.load(handoff[label + '_controller']['path'])
        outer = O.load(handoff[label + '_outer']['path'])
        require(rec['complete'] is True and rec['phase'] == phase and rec['source'] == str(source)
                and rec['outer'] == handoff[label + '_outer']
                and rec['environment'] == handoff['environment'], 'ordinary controller binding')
        require(rec['adapter_code_pins'] == {str(ordinary / 'controller.py'): ADAPTER_PINS[role]},
                'ordinary adapter identity')
        O.check_pins(rec['source_pins'])
        O.check_pins(rec['toolchain_files'])
        for evidence in rec['toolchain_evidence']:
            O.verify_pin(evidence)
        clean_outer(outer, argv=rec['command'], cwd=source, output=ordinary / label / 'outer',
                    bound=ordinary, epoch=rec['epoch'], locks=rec['locks'],
                    seconds=600 if phase == 'BUILD' else 120)
        watchdog = O.load(O.verify_pin(rec['original_watchdog']))
        require(watchdog['complete'] is True and watchdog['exit_code'] == 0 and watchdog['reason'] is None
                and watchdog['samples'][-1]['group_rss'] == 0, 'ordinary watchdog incomplete')
        controllers[phase] = rec
    require(controllers['BUILD']['producer_receipt'] == handoff['receipt']
            and controllers['CONTROLS']['controls'] == handoff['controls'], 'ordinary result binding')
    for key in ('epoch', 'environment', 'source_pins', 'toolchain_files', 'toolchain_evidence'):
        require(controllers['BUILD'][key] == controllers['CONTROLS'][key], 'ordinary stages drifted: ' + key)
    controls = O.load(handoff['controls']['path'])
    require(controls['complete'] is True and controls['full_object_inputs_verified'] is True
            and controls['producer_receipt'] == handoff['receipt']
            and len(controls['commands']) == len(CASES), 'five successful ordinary controls required')
    for row, (label, args, status, out, err) in zip(controls['commands'], CASES):
        require(row['label'] == label and row['passed'] is True and row['exit_code'] == status
                and row['argv'] == [auth['outputs']['emlf']['path'], *args]
                and row['cwd'] == str(source), 'ordinary CLI control identity')
        require(O.verify_pin(row['stdout']).read_bytes() == out
                and O.verify_pin(row['stderr']).read_bytes() == err, 'ordinary CLI result mismatch')
    relink = O.load(handoff['relink']['path'])
    spec = O.load(I / 'insertion-map.json')
    names = spec['emlf_modules']
    require(relink['complete'] is True and relink['source_commit'] == COMMITS[role]
            and relink['source'] == str(source) and relink['producer'] == str(producer)
            and relink['producer_receipt'] == handoff['receipt'] and relink['non_main_count'] == 94
            and len(names) == len(set(names)) == 94
            and [x['module'] for x in relink['non_main_closure']] == names, 'exact original Emlf closure required')
    for row in relink['non_main_closure']:
        for key, suffix in (('object', '.o'), ('interface', '.hi')):
            expected = producer / 'objects' / (row['module'].replace('.', '/') + suffix)
            require(O.verify_pin(row[key]) == expected
                    and row[key]['sha256'] == auth['object_inputs'][str(expected.relative_to(producer))],
                    'closure object/interface mismatch')
    require([x['label'] for x in relink['c_objects']] == ['host', 'supervisor'], 'two C objects required')
    for row in relink['c_objects']:
        require(O.verify_pin(row['object']) == producer / (row['label'] + '.o')
                and row['original_command'] in auth['commands'], 'C object command binding')
        O.verify_pin(row['source'])
    require(O.verify_pin(relink['original_main']) == source / 'host/ghc/app/emlf/Main.hs'
            and relink['original_main_link_command'] in auth['commands'], 'original Emlf Main provenance')
    return {'oracle': oracle, 'source': source, 'producer': producer, 'auth': auth,
            'handoff': handoff, 'relink': relink}


def import_flags(auth, producer, destination):
    """Only import/output routing changes; package/optimization/demand flags stay."""
    result, i = [], 0
    flags = auth['flags']
    while i < len(flags):
        flag = flags[i]
        if flag in ('-odir', '-hidir'):
            i += 2
        elif flag == '-i' or flag.startswith('-i'):
            i += 1
        else:
            result.append(flag)
            i += 1
    return [*result, '-i', '-i' + str(producer / 'objects'),
            '-odir', str(destination), '-hidir', str(producer / 'objects')]


def fixture_expected(mode):
    ids = PURE_IDS if mode == 'pure' else PUBLICATION_IDS
    return (''.join('PASS\t' + x + '\n' for x in ids)
            + 'SUMMARY\t' + mode + '\t' + str(len(ids)) + '\n').encode()


def summarise(samples):
    require(len(samples) == 12 and [x['role'] for x in samples] == SEQUENCE
            and all(x['complete'] is True for x in samples), 'no summary for incomplete ABBA*3')
    metrics = {}
    for key in ('guard_wall_seconds', 'rts_allocated_bytes'):
        a = [x[key] for x in samples if x['role'] == 'A']
        b = [x[key] for x in samples if x['role'] == 'B']
        ma, mb = statistics.median(a), statistics.median(b)
        pairs = []
        for n in range(0, 12, 2):
            pair = {x['role']: x for x in samples[n:n + 2]}
            av, bv = pair['A'][key], pair['B'][key]
            require(av > 0 and bv > 0, 'positive ordinary metric required')
            pairs.append({'indices': [n + 1, n + 2], 'order': ''.join(x['role'] for x in samples[n:n + 2]),
                          'A': av, 'B': bv, 'baseline_over_candidate': av / bv,
                          'candidate_relative_change': bv / av - 1})
        metrics[key] = {'A_values': a, 'B_values': b, 'A_median': ma, 'B_median': mb,
                        'median_ratio_A_over_B': ma / mb, 'candidate_median_relative_change': mb / ma - 1,
                        'adjacent_pairs': pairs,
                        'adjacent_ratio_median': statistics.median(x['baseline_over_candidate'] for x in pairs)}
    return {'domain': 'ordinary non-profiled relinks, compiled-in RTS -s, fresh foundation14',
            'metrics': metrics,
            'limitations': 'Guard wall and whole-process RTS allocated bytes are separate domains. '
                'No exclusive attribution, native-generation result, profiled allocation equality, '
                'statistical significance, or general workload speedup is inferred.'}


class Worker:
    def __init__(self, phase, path, digest):
        self.a, self.work = validate_admission(path, digest, phase)
        self.phase, self.path, self.digest = phase, path, digest
        self.folder, self.outer = phase_paths(self.work, phase)
        self.start = time.monotonic()
        self.command_count = 0
        require(dict(os.environ) == self.a['environment'], 'worker environment differs')
        self.scope()
        O.absent(self.folder)
        self.folder.mkdir()
        (self.folder / 'commands').mkdir()
        self.record = {'schema': 'r15-ordinary-worker-v1', 'complete': False, 'phase': phase,
            'admission': O.pin(path), 'worker_command': worker_command(phase, path, digest),
            'input_pins': {}, 'output_pins': {}, 'commands': [], 'samples': [],
            'native_fixed_point_ab': False, 'interpretation': 'Ordinary paired validation/measurement only.'}
        for key in ('work', 'code_pins', 'fixture_pins', 'reference_pins', 'ordinary', 'environment', 'epoch', 'locks'):
            self.record[key] = self.a[key]
        self.record['input_pins'].update(self.a['code_pins'])
        self.record['input_pins'].update(self.a['fixture_pins'])
        self.record['input_pins'].update(self.a['reference_pins'])
        self.sides = {}
        self.binaries = {}
        self.save()

    def save(self):
        O.save(self.folder / 'receipt.json', self.record)

    def scope(self):
        return G.verify_worker_scope(worker_command(self.phase, self.path, self.digest),
            cwd=HERE, output=self.outer, locks=self.a['locks'], epoch=self.a['epoch'],
            seconds=600, bounded_root=self.work,
            claim_path=self.work / 'claims' / (self.phase + '.json'),
            claim_expected=claim(self.phase, self.path))

    def remember(self, path, output=False):
        p = O.pin(path)
        self.record['output_pins' if output else 'input_pins'][p['path']] = p['sha256']
        return p

    def provenance(self):
        for role in ('A', 'B'):
            side = verify_side(role, self.a['ordinary'][role])
            self.sides[role] = side
            auth = side['auth']
            self.remember(self.a['ordinary'][role]['path'])
            for value in side['handoff'].values():
                if isinstance(value, dict) and 'path' in value and 'sha256' in value:
                    O.verify_pin(value)
                    self.remember(value['path'])
            for group in ('toolchain', 'installed_dependencies'):
                self.record['input_pins'].update(auth[group]['files'])
            for group in ('shared_inputs', 'host_inputs', 'configuration_inputs', 'outputs'):
                for item in auth[group].values():
                    self.record['input_pins'][item['path']] = item['sha256']
            for relative, sha in auth['object_inputs'].items():
                self.record['input_pins'][str(side['producer'] / relative)] = sha
            for name in ('ghc', 'cc', 'orchestrator'):
                self.record['input_pins'][auth[name]['path']] = auth[name]['sha256']
        require(self.sides['A']['auth']['toolchain'] == self.sides['B']['auth']['toolchain']
                and self.sides['A']['auth']['installed_dependencies'] == self.sides['B']['auth']['installed_dependencies']
                and self.sides['A']['auth']['package_database_sha256']
                    == self.sides['B']['auth']['package_database_sha256'], 'paired toolchain/package mismatch')
        self.reference()
        self.save()

    def reference(self):
        qpath = R / 'profile-r14-01/stages/QUALIFY/receipt.json'
        tpath = R / 'profile-r14-01/stages/TARGET-QUALIFICATION/receipt.json'
        q, t = O.load(qpath), O.load(tpath)
        for phase, receipt in (('QUALIFY', q), ('TARGET-QUALIFICATION', t)):
            require(receipt['complete'] is True and receipt['phase'] == phase
                    and receipt['ordinary_receipt'] == self.sides['A']['handoff']['receipt'],
                    'reference must derive from the authenticated r14 ordinary producer')
            clean_outer(O.load(R / ('profile-r14-01/guards/' + phase + '/guard.json')),
                argv=receipt['worker_command'], cwd=I,
                output=R / ('profile-r14-01/guards/' + phase), bound=R / 'profile-r14-01',
                epoch=receipt['epoch'], seconds=180 if phase == 'QUALIFY' else 420)
        require(q['builtin_setup']['complete'] is True and q['builtin_setup']['prefix'] == str(BUILTIN),
                'fixed authenticated r14 builtin required')
        for suffix in O.SUFFIXES[:2]:
            p = str(BUILTIN) + suffix
            require(q['output_pins'][p] == O.sha(p), 'fixed builtin differs from r14 qualification')
        legs = [x for x in t['legs'] if x['role'] == 'ordinary-Q']
        require(len(legs) == 1 and legs[0]['complete'] is True and legs[0]['fresh'] == 475
                and legs[0]['reused'] == 0 and legs[0]['all14_owners_checked'] is True
                and legs[0]['builtin_checked'] is True and legs[0]['full_ordered_query_checked'] is True,
                'r14 ordinary-Q reference incomplete')
        for p, sha in O.three_artifacts(REFERENCE).items():
            require(t['output_pins'][p] == sha, 'ordinary-Q reference changed')
        self.foundation = O.foundation(R / 'source', I / 'foundation14-source.json')

    def recheck(self, full=False):
        require(O.sha(self.path) == self.digest, 'admission changed')
        O.check_pins(self.a['code_pins'])
        O.check_pins(self.a['fixture_pins'])
        for binary in self.binaries.values():
            O.verify_pin(binary)
        if full:
            O.check_pins(self.record['input_pins'])
            O.check_pins(self.record['output_pins'])
            for role, side in self.sides.items():
                now = verify_side(role, self.a['ordinary'][role])
                require(now['auth'] == side['auth'], 'producer/source/package authentication changed')
            O.foundation(R / 'source', I / 'foundation14-source.json')

    def command(self, label, argv, *, cwd, maximum=30, reports=(), accepted=(0,),
                expected_out=None, expected_err=None):
        self.recheck()
        self.command_count += 1
        output = self.folder / 'commands' / ('%03d-%s' % (self.command_count, label))
        left = 600 - (time.monotonic() - self.start) - 2
        require(left > 0, 'stage deadline exhausted')
        seconds = min(maximum, left)
        argv = list(map(str, argv))
        for report in reports:
            O.absent(report)
        row = G.run_child(argv, cwd=cwd, output=output, seconds=seconds,
                          reports=reports, bounded_root=self.work, accepted_exit_codes=accepted)
        self.record['commands'].append({'label': label, 'receipt': O.pin(output / 'guard.json')
            if (output / 'guard.json').is_file() else None, 'guard': row})
        self.save()
        require(row['complete'] is True and row['cleanup'] is True and row['reason'] is None
                and row['test_only'] is False and row['standalone_admission'] is False
                and row['exit_code'] in accepted and row['locks'] == [] and row['epoch'] is None
                and row['lock_reacquired'] is False and row['command'] == argv
                and row['cwd'] == str(cwd) and row['output'] == str(output)
                and row['bounded_root'] == str(self.work) and row['limits'] == G.LIMITS
                and row['seconds'] == seconds, 'bounded command failed: ' + label)
        require(set(row['archived']) == set(map(str, reports)), 'exact report archive required')
        for name in ('guard.json', 'guard-config.json', 'stdout', 'stderr'):
            self.remember(output / name, True)
        require(O.sha(output / 'guard-config.json') == row['config_sha256'], 'child config changed')
        for report in row['archived'].values():
            self.remember(O.verify_pin(report), True)
        out, err = (output / 'stdout').read_bytes(), (output / 'stderr').read_bytes()
        require(expected_out is None or out == expected_out, 'exact stdout mismatch: ' + label)
        require(expected_err is None or err == expected_err, 'exact stderr mismatch: ' + label)
        self.recheck()
        return out, err, row

    def build_main(self, role, name, source, *, filepath=False, stats=False):
        side = self.sides[role]
        destination = self.folder / role / name
        destination.mkdir(parents=True, exist_ok=False)
        flags = import_flags(side['auth'], side['producer'], destination)
        if filepath:
            require(any('/filepath-' in p and p.endswith('/System/FilePath.hi')
                        for p in side['auth']['installed_dependencies']['files']),
                    'fixture-only filepath package must already be authenticated')
            flags += ['-package', 'filepath']
        main_o, main_hi = destination / 'Main.o', destination / 'Main.hi'
        ghc = side['auth']['ghc']['path']
        self.command(role + '-compile-' + name,
            [ghc, '-c', '-fforce-recomp', *flags, source, '-o', main_o, '-ohi', main_hi],
            cwd=side['source'], maximum=180)
        self.remember(main_o, True)
        self.remember(main_hi, True)
        binary = destination / 'program'
        objects = [row['object']['path'] for row in side['relink']['non_main_closure']]
        extra_modules = ['Package.Distribution', 'Package.Release'] if name == 'artifact-binary' else []
        for module_name in extra_modules:
            for suffix in ('.o', '.hi'):
                relative = 'objects/' + module_name.replace('.', '/') + suffix
                p = side['producer'] / relative
                require(O.sha(p) == side['auth']['object_inputs'][relative], 'extra fixture object/interface changed')
                self.remember(p)
                if suffix == '.o':
                    require(str(p) not in objects, 'duplicate fixture object')
                    objects.append(str(p))
        c_objects = [row['object']['path'] for row in side['relink']['c_objects']]
        options = ['-rtsopts=ignoreAll']
        if stats:
            options += ['-with-rtsopts=-s' + str(self.work / 'active' / (role + '.stats'))]
        require(not any('-prof' in f or f.startswith('-fprof') for f in flags), 'ordinary only')
        self.command(role + '-link-' + name,
            [ghc, *flags, *options, main_o, *objects, *c_objects, '-o', binary],
            cwd=side['source'], maximum=180)
        pin = self.remember(binary, True)
        self.record.setdefault('builds', []).append({'role': role, 'kind': name, 'source': O.pin(source),
            'flags': flags, 'main_object': O.pin(main_o), 'main_interface': O.pin(main_hi),
            'binary': pin, 'emlf_closure_count': 94, 'linked_non_main_count': len(objects),
            'extra_fixture_modules': extra_modules,
            'statistics_path': str(self.work / 'active' / (role + '.stats')) if stats else None})
        self.save()
        return pin

    def pin_tree(self, root):
        for p in sorted(root.rglob('*')):
            O.safe(p, True)
            if p.is_file():
                self.remember(p, True)

    def validate(self):
        for role in ('A', 'B'):
            side = self.sides[role]
            fixture = self.build_main(role, 'encode-input-reuse', FIXTURE, filepath=True)
            for mode in ('pure', 'publication'):
                args = [fixture['path'], mode]
                if mode == 'publication':
                    root = self.folder / role / 'encode-publication'
                    O.absent(root)
                    args.append(str(root))
                self.command(role + '-encode-' + mode, args, cwd=side['source'], maximum=90,
                             expected_out=fixture_expected(mode), expected_err=b'')
                if mode == 'publication':
                    self.pin_tree(root)
            self.maintenance(role)
            if role == 'B':
                require(FIRST_FAILURE_EXPECTED.read_bytes() == FIRST_FAILURE_OUTPUT,
                        'first-failure exact expected output changed')
                extra = self.build_main(role, 'encode-first-failure', FIRST_FAILURE)
                self.command('B-first-failure', [extra['path']], cwd=side['source'],
                             maximum=30, expected_out=FIRST_FAILURE_OUTPUT, expected_err=b'')
            binary = self.build_main(role, 'ordinary-emlf',
                                     side['source'] / 'host/ghc/app/emlf/Main.hs', stats=True)
            self.binaries[role] = binary
            for label, args, status, out, err in CASES:
                report = self.work / 'active' / (role + '.stats')
                _, _, row = self.command(role + '-cli-' + label, [binary['path'], *args],
                    cwd=side['source'], maximum=30, reports=[report], accepted=(status,),
                    expected_out=out, expected_err=err)
                STATS.parse_statistics(O.verify_pin(row['archived'][str(report)]).read_bytes())
        self.record['binaries'] = self.binaries
        self.record['validation'] = {'encode_pure_cases_each': 18, 'encode_publication_cases_each': 4,
            'real_cli_controls_each': 5, 'maintenance_modes_each': 3,
            'candidate_first_encoding_left_and_finite_cases': 2,
            'limits': 'No equivalence claim for OOM, asynchronous cancellation, or a hypothetical second encoding IO failure.',
            'source_level_native_regression_claimed': False}

    def maintenance(self, role):
        # Exact expected outputs are pinned alongside the fixture sources.
        side = self.sides[role]
        for name, modes in (('query-index', ('pure', 'publication')),
                            ('artifact-binary', ('root-bounds',))):
            fixture = self.build_main(role, name, side['source'] / FIXTURE_RELATIVES[name])
            for mode in modes:
                args = [fixture['path'], mode]
                if mode == 'publication':
                    root = self.folder / role / 'query-index-publication'
                    O.absent(root)
                    args.append(str(root))
                expected = MAINTENANCE_OUTPUTS[(name, mode)]
                self.command(role + '-' + name + '-' + mode, args, cwd=side['source'],
                             maximum=90, expected_out=expected, expected_err=b'')
                if mode == 'publication':
                    self.pin_tree(root)

    def show(self, role, prefix, identity, modules, dependencies, label):
        binary = self.sides[role]['auth']['outputs']['emlf']['path']
        out, _, row = self.command(label, [binary, '--show-crate', str(prefix) + '.mlfci'],
            cwd=R / 'source', expected_err=b'')
        O.interface(out.decode('utf-8'), identity, modules, dependencies)
        return row

    def bench(self):
        prior = O.load(self.a['prior']['receipt']['path'])
        self.binaries = prior['binaries']
        require(set(self.binaries) == {'A', 'B'}, 'two validated ordinary binaries required')
        self.record['input_pins'].update(prior['output_pins'])
        for role in ('A', 'B'):
            O.verify_pin(self.binaries[role])
            self.show(role, BUILTIN, O.BUILTIN, ['Prelude', 'MLF.Primitive'], {}, role + '-fixed-builtin')
        for index, role in enumerate(SEQUENCE, 1):
            folder = self.folder / ('%02d-%s' % (index, role))
            folder.mkdir()
            queries = folder / 'queries'
            queries.mkdir()
            require(not list(queries.iterdir()), 'new empty per-sample query directory required')
            prefix, spec = folder / 'unit', folder / 'crate.spec'
            fields = ['MLF-CRATE-1', O.IDENTITY, '', 'false',
                O.pack([O.pack([row['module'], str(R / 'source' / row['relative'])]) for row in self.foundation]),
                O.pack([str(BUILTIN) + '.mlfci']), str(queries), str(BUILTIN)]
            spec.write_text(O.pack(fields), encoding='utf-8')
            require(O.unpack(spec.read_text()) == fields, 'exact r14 workload configuration required')
            self.remember(spec, True)
            for suffix in O.SUFFIXES:
                O.absent(str(prefix) + suffix)
            O.check_pins(self.a['reference_pins'])
            O.foundation(R / 'source', I / 'foundation14-source.json')
            report = self.work / 'active' / (role + '.stats')
            _, _, row = self.command('sample-%02d-%s' % (index, role),
                [self.binaries[role]['path'], '--compile-crate', spec, '-o', prefix],
                cwd=R / 'source', maximum=180, reports=[report], expected_out=b'', expected_err=b'')
            statistics_row = STATS.parse_statistics(O.verify_pin(row['archived'][str(report)]).read_bytes())
            artifacts = O.three_artifacts(prefix, REFERENCE)
            self.record['output_pins'].update(artifacts)
            shown = self.show(role, prefix, O.IDENTITY, [x['module'] for x in self.foundation],
                              {O.BUILTIN: str(BUILTIN) + '.mlfci'}, 'owners-%02d-%s' % (index, role))
            lock = O.regular(queries / '.lock')
            info = lock.stat()
            G.reacquire_locks([{'path': str(lock), 'device': info.st_dev, 'inode': info.st_ino, 'kind': 'posix'}])
            O.check_pins(self.a['reference_pins'])
            sample = {'index': index, 'role': role, 'complete': True,
                'fresh': 475, 'reused': 0, 'all14_owners_checked': True, 'builtin_checked': True,
                'full_ordered_queries_checked': True, 'three_raw_bytes_equal_r14': True,
                'query_lock_reacquired': True, 'guard_wall_seconds': row['elapsed_seconds'],
                'rts_allocated_bytes': statistics_row['allocated_bytes'], 'rts_statistics': statistics_row,
                'binary': self.binaries[role], 'spec': O.pin(spec), 'artifacts': artifacts,
                'compile_guard': row, 'interface_guard': shown}
            self.record['samples'].append(sample)
            self.save()
        require([x['role'] for x in self.record['samples']] == SEQUENCE, 'complete ABBA*3 required')
        # No performance summary until launch sees final outer cleanup.

    def run(self):
        try:
            self.provenance()
            self.recheck(full=True)
            if self.phase == 'VALIDATE':
                self.validate()
            else:
                self.bench()
            self.recheck(full=True)
            self.scope()
            require(time.monotonic() - self.start < 600, 'stage deadline')
            self.record.update(complete=True, elapsed_seconds=time.monotonic() - self.start)
        except BaseException as exc:
            self.record.update(complete=False, error=repr(exc),
                               elapsed_seconds=time.monotonic() - self.start)
            raise
        finally:
            self.save()


def launch(phase, path, digest):
    a, work = validate_admission(path, digest, phase)
    O.absent(G.epoch_active_path(a['locks'], a['epoch']))
    for name in ('claims', 'guards', 'stages', 'tmp', 'active'):
        O.safe(work / name)
        (work / name).mkdir(exist_ok=True)
        require((work / name).is_dir(), 'bounded work directory required')
    folder, outer = phase_paths(work, phase)
    O.absent(folder)
    O.absent(outer)
    cpath = work / 'claims' / (phase + '.json')
    with cpath.open('x') as stream:
        json.dump(claim(phase, path), stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    argv = worker_command(phase, path, digest)
    os.environ.clear()
    os.environ.update(a['environment'])
    row = G.run_guard(argv, cwd=HERE, output=outer, locks=a['locks'], epoch=a['epoch'],
                      seconds=600, bounded_root=work)
    # Fail closed before final completion or any speedup summary.
    clean_outer(row, argv=argv, cwd=HERE, output=outer, bound=work,
                epoch=a['epoch'], locks=a['locks'], seconds=600)
    receipt = O.load(folder / 'receipt.json')
    require(receipt['complete'] is True and receipt['phase'] == phase
            and receipt['admission'] == O.pin(path), 'worker did not complete the admitted phase')
    O.check_pins(receipt['input_pins'])
    O.check_pins(receipt['output_pins'])
    final = {'schema': 'r15-ordinary-final-v1', 'phase': phase, 'complete': True,
             'admission': O.pin(path), 'worker_receipt': O.pin(folder / 'receipt.json'),
             'outer': O.pin(outer / 'guard.json'), 'native_fixed_point_ab': False}
    if phase == 'BENCH':
        final['ordinary_comparison'] = summarise(receipt['samples'])
    O.save(folder / 'final.json', final)
    print(json.dumps(final, indent=2, sort_keys=True))


def draft(phase, work, review, destination):
    """Pin a draft only, never grant approval or run anything."""
    work = work_path(work)
    if phase == 'VALIDATE':
        O.absent(work)
        work.mkdir()
    else:
        O.safe(work, True)
    for name in ('claims', 'guards', 'stages', 'tmp', 'active'):
        O.safe(work / name)
        (work / name).mkdir(exist_ok=True)
        require((work / name).is_dir(), 'bounded work directory required')
    epoch_pin = O.pin(N / 'coordination/lock-epoch.json')
    epoch = O.load(epoch_pin['path'])
    env = O.load(N / 'coordination/environment.json')
    env['TMPDIR'] = str(work / 'tmp')
    folder, outer = phase_paths(work, 'VALIDATE')
    a = {'schema': 'r15-ordinary-validation-admission-v1', 'approved': False, 'phase': phase,
        'work': str(work), 'budget_seconds': 600, 'per_compile_seconds': 180,
        'sequence': SEQUENCE, 'commits': COMMITS, 'native_fixed_point_ab': False,
        'code_pins': code_pins(), 'fixture_pins': expected_fixture_pins(),
        'reference_pins': reference_pins(), 'review': O.pin(review),
        'python': O.pin(Path(sys.executable).resolve()), 'environment': env,
        'epoch': epoch_pin, 'locks': [epoch['shared'], epoch['reproduction']],
        'ordinary': {role: O.pin(root / 'ordinary/ordinary-handoff.json') for role, root in ROOTS.items()},
        'prior': {} if phase == 'VALIDATE' else {'receipt': O.pin(folder / 'receipt.json'),
            'outer': O.pin(outer / 'guard.json'), 'final': O.pin(folder / 'final.json')}}
    O.absent(destination)
    O.save(destination, a)
    print(json.dumps({'draft': O.pin(destination), 'approved': False}))


def main():
    initialise()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('run', '_worker'):
        p = sub.add_parser(action)
        p.add_argument('phase', choices=list(BUDGETS))
        p.add_argument('--admission', type=Path, required=True)
        p.add_argument('--sha256', required=True)
    sub.add_parser('inventory')
    p = sub.add_parser('draft')
    p.add_argument('phase', choices=list(BUDGETS))
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--review', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'inventory':
        print(json.dumps({'complete': False, 'review_scope': 'static runner and fixture review required',
                          'code_pins': code_pins(), 'fixture_pins': expected_fixture_pins()},
                         indent=2, sort_keys=True))
    elif args.action == 'draft':
        draft(args.phase, args.work, args.review, args.output)
    elif args.action == 'run':
        launch(args.phase, args.admission, args.sha256)
    else:
        Worker(args.phase, args.admission, args.sha256).run()


# Exact stdout expectations for the three approved maintenance modes.
MAINTENANCE_OUTPUTS = {
    ('query-index', 'pure'): (
        b'PASS legacy and v2 exact roundtrip, order, repeated reads, independent location\n'
        b'PASS typed IDs, dictionary/row canonicality, closure, hashes, legacy rejection\n'
        b'PASS actual 4096/4097 depth boundary independent of key order\n'
        b'PASS referenced and codec budgets, exact 64/256 Mi boundaries, long-prefix attack\n'),
    ('query-index', 'publication'):
        b'PASS cold/warm publication, all failpoints, retained payload SHA, generation SHA\n',
    ('artifact-binary', 'root-bounds'): b'PASS root-bounds\n',
}

if __name__ == '__main__':
    main()
