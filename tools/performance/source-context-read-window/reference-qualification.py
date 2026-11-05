#!/usr/bin/env python3
"""Current foundation504 qualification. False draft is not execution authority."""
from pathlib import Path
import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
import types

R = Path('/workspace/scratch/3f83e2ebe290/full88-work-20261031T0843Z')
P = R/'preflight/optimization-readonly-20261031/artifact-query-scratch-cleanup-20261101T1422Z/context-read-window-20261102T0406Z'
HISTORICAL_P = R/'preflight/optimization-readonly-20261031/artifact-query-scratch-cleanup-20261101T1422Z/merge-ready-publication-20261101T2110Z'
S, PRODUCER, W = P/'candidate', P/'producer', P/'workload-foundation'
PREP, BUILD, EV = W/'preparation', W/'build', W/'qualification-evidence'
FINAL = PREP/'qualification-plan.json'
BH = P/'build-preparation/run-build-r1.py'
BP = P/'build-preparation/build-plan.json'
BD = P/'build-preparation/build-plan-draft.json'
FH = P/'fixture-preparation-revision1/run-fixture.py'
FP = P/'fixture-preparation-revision1/fixture-plan.json'
IR = W/'run_foundation.py'
TEMPLATE = W/'study-plan-draft.json'
PYTHON = '/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3.12'
MIB = 1024**2
SHA = re.compile('[0-9a-f]{64}')
LIMITS = {'seconds':1800,'address_space_mib':6144,'rss_mib':5120,
          'root_output_mib':8192,'disk_free_mib':4096,
          'mem_available_floor_bytes':3072*MIB}
FIXED = {'/workspace/scratch/3f83e2ebe290/full88-work-20261031T0843Z/preflight/optimization-readonly-20261031/artifact-query-scratch-cleanup-20261101T1422Z/context-read-window-20261102T0406Z/build-preparation/run-build-r1.py': '87f6ccd3d9e5b5b41ddd16ed6a46f1fe5a756b5586e2f631b7040cc81b8d1493', '/workspace/scratch/3f83e2ebe290/full88-work-20261031T0843Z/preflight/optimization-readonly-20261031/artifact-query-scratch-cleanup-20261101T1422Z/context-read-window-20261102T0406Z/build-preparation/build-plan-draft.json': '0e5d5f683b07668bc2aa4be1d8b4eb8d3a3cebfaa0a672c8b3a3e8e55dc5ba32', '/workspace/scratch/3f83e2ebe290/full88-work-20261031T0843Z/preflight/optimization-readonly-20261031/artifact-query-scratch-cleanup-20261101T1422Z/context-read-window-20261102T0406Z/workload-foundation/FoundationStudy.hs': '86effd0440ff90eef37a11a52f36d8eaed4d88f9247acd0ff0b098289278f663', '/workspace/scratch/3f83e2ebe290/full88-work-20261031T0843Z/preflight/optimization-readonly-20261031/artifact-query-scratch-cleanup-20261101T1422Z/context-read-window-20261102T0406Z/workload-foundation/run_foundation.py': '942632fbd79d65847f3f95f052bce8a098ea0c1d84adcba6a4a9396eacf0bf4d', '/workspace/scratch/3f83e2ebe290/full88-work-20261031T0843Z/preflight/optimization-readonly-20261031/artifact-query-scratch-cleanup-20261101T1422Z/context-read-window-20261102T0406Z/workload-foundation/study-plan-draft.json': '449bca98e0dd8de598c3f35fd18ec827168cf16dc15c8ea251ef5d593400e4fc', '/workspace/scratch/3f83e2ebe290/full88-work-20261031T0843Z/preflight/optimization-readonly-20261031/artifact-query-scratch-cleanup-20261101T1422Z/context-read-window-20261102T0406Z/workload-foundation/README-DRAFT.md': '6998a9ed38b1a134300bd8017d5ee82bbdef4253b623f6887a6af5cda08f1df5'}
SOURCE_HASHES = '8e91aa4afbdf6cc57cf0f790874b6865f65ecf4d8afa58e3a8dd76b66a294bee'
SOURCE_STATE = '2c9971a1532248370967f4c32252b399593b3dbf5022d2cf4b669021f19d0e42'
ORDER = ['coldA','materializeB','warmA1','warmB1','warmB2','warmA2',
         'changeA','changeB','changedwarmA','changedwarmB']
PRIVATE = [W/name for name in ('home','tmp','cache')]
OLD = HISTORICAL_P/'workload-foundation'
OLD_PREFIX = OLD/'run/outputs/coldA/unit'
OLD_INDEX = OLD/'run/metadata/cold.index'
OLD_BUILTIN = OLD/'run/builtin/unit'
NEGATIVE_STDERR = (b"foundation-study: Uncaught exception ghc-internal:GHC.Internal.Exception.ErrorCall:\n\n"
                   b"Version oracle mismatch: expected 0.3.1; actual 0.3.0\n")
POSITIVE_STDOUT = b"PASS 504 finalized fragments and independent Version RString\n"


def need(value, message):
    if not value:
        raise RuntimeError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode()


def stamp(path):
    x = path.lstat()
    return [x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns,x.st_mode]


def small(path, maximum=2*MIB):
    before = stamp(path)
    need(stat.S_ISREG(before[5]) and before[2] <= maximum and
         path.resolve(strict=True) == path and path.lstat().st_nlink == 1,
         'bounded canonical regular input: '+str(path))
    raw = path.read_bytes()
    need(stamp(path) == before and len(raw) == before[2], 'input changed while reading')
    return raw


def read_json(path, maximum=2*MIB):
    return json.loads(small(path, maximum), object_pairs_hook=unique)


def load_module(path, expected, name):
    raw = small(path, 64*1024)
    need(digest(raw) == expected, 'pinned helper changed: '+str(path))
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def guard_argv(plan_sha):
    return [str(R/'run-guarded.sh'),'--seconds','1800','--address-space-mib','6144',
            '--rss-mib','5120','--max-output-mib','8192','--disk-free-mib','4096',
            str(W/'guard'),PYTHON,'-I','-B',str(PREP/'run-qualified-foundation.py'),plan_sha]


def environment():
    return {'PATH':str(R/'toolchains/ghc-9.14.1/bin')+':/usr/bin:/bin',
            'HOME':str(PRIVATE[0]),'TMPDIR':str(PRIVATE[1]),'TMP':str(PRIVATE[1]),
            'TEMP':str(PRIVATE[1]),'XDG_CACHE_HOME':str(PRIVATE[2]),
            'XDG_CONFIG_HOME':str(PRIVATE[0]/'config'),'XDG_DATA_HOME':str(PRIVATE[0]/'data'),
            'LC_ALL':'C.UTF-8','LANG':'C.UTF-8','TZ':'UTC','GHC_ENVIRONMENT':'-',
            'GHCRTS':'','GHC_CHARENC':'UTF-8','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}


def guard_ok(path):
    g = read_json(path)
    need(g.get('complete') is True and g.get('exit_code') == 0 and
         g.get('cleanup_kernel_wait_no_children') is True and
         g.get('descendant_observation_complete') is True and
         not g.get('remaining_descendants') and not g.get('cleanup_errors') and
         not g.get('process_scan_errors') and g.get('reason') is None,
         'successful no-child predecessor guard required: '+str(path))


def support(plan):
    L = load_module(BH, FIXED[str(BH)], 'current_foundation_source_checks')
    need((L.R,L.D,L.S,L.OUT) == (R,P,S,PRODUCER), 'actual build-helper roots')
    bp = read_json(BP, 128*1024)
    need(bp['approved_for_execution'] is True and bp['source_root'] == str(S) and
         bp['producer'] == str(PRODUCER), 'actual current build plan')
    need(len(bp['source_sha256']) == 186 and len(bp['source_state']) == 255 and
         digest(canonical(bp['source_sha256'])) == SOURCE_HASHES and
         digest(canonical(bp['source_state'])) == SOURCE_STATE, 'frozen current186/255 source')
    bd = read_json(BD,128*1024)
    need(bp['source_sha256'] == bd['source_sha256'] and bp['source_state'] == bd['source_state'] and
         bp['tool_pins'] == bd['tool_pins'] and bp['tool_bindings'] == bd['tool_bindings'],
         'final build cannot replace frozen source/tool inputs')
    F = load_module(FH, plan['input_sha256'][str(FH)], 'current_foundation_control_checks')
    need((F.R,F.D,F.S,F.PRODUCER,F.OUT) == (R,P,S,PRODUCER,P/'context-controls-revision1'),
         'actual maintained40R1 helper roots')
    I = load_module(IR, FIXED[str(IR)], 'current_foundation_frozen_study')
    need((I.ROOT,I.PUBLICATION,I.WORK) == (R,P,W) and I.ORDER == ORDER and
         sum(I.CAPS_MIB.values()) == 448, 'frozen inner study roots/order/caps')
    return L,bp,F,I


def pin_check(plan, L, bp):
    L.source_check(bp)
    L.tools_check(bp)
    for path, h in plan['input_sha256'].items():
        need(digest(small(Path(path),4*MIB)) == h, 'immutable input changed: '+path)
    need(digest(canonical(L.closed(PRODUCER))) == plan['producer_state']['closed_tree_sha256'],
         'actual complete producer path/stat closure changed')
    need(L.sha(PRODUCER/'receipt.json',4*MIB) == plan['producer_state']['receipt_sha256'],
         'current producer receipt changed')


def prerequisites(plan, L, bp, F):
    fp = read_json(FP, 2*MIB)
    need(fp['approved_for_execution'] is True, 'actual reviewed40R1 plan')
    F.pin_check(fp,L,bp)  # actual current232, build, source, tools and producer checks
    for q in (P/'unit-preparation-revision1/unit-guard/bounded-receipt.json',
              P/'producer-build-guard/bounded-receipt.json',
              P/'context-controls-guard-revision1/bounded-receipt.json'):
        need(str(q) in plan['input_sha256'], 'predecessor guard omitted from pins')
        guard_ok(q)
    be = read_json(P/'build-evidence/receipt.json')
    need(be['complete'] is True and be['driver_exit_code'] == 0 and
         be['post_source_unchanged'] is True and be['post_selected_tools_unchanged'] is True and
         be['plan_sha256'] == plan['input_sha256'][str(BP)], 'actual current build evidence')
    fe = read_json(P/'fixture-evidence-revision1/receipt.json')
    need(fe['complete'] is True and fe['exit_code'] == 0 and
         fe['inputs_and_producer_unchanged_after'] is True and
         fe['plan_sha256'] == plan['input_sha256'][str(FP)], 'actual current40R1 qualification')
    producer = read_json(PRODUCER/'receipt.json',4*MIB)
    qualification = L.audit_producer(bp)  # real TD.authenticate_build, never a substitute root
    need(qualification['receipt_sha256'] == plan['producer_state']['receipt_sha256'],
         'maintained actual producer authentication')
    controls = F.audit(fp,L,producer)  # reuse already maintained full40R1 audit, no new readback algorithm
    baseline = plan['baseline_counterexample_acceptance']
    need(isinstance(baseline,dict) and baseline.get('independent_readback_reviewed') is True and
         baseline.get('first_guard_status') == 'failed-audit-cap-evidence-retained' and
         baseline.get('candidate_qualification_claimed') is False and
         baseline.get('proof_inputs') and isinstance(baseline.get('review_summary'),str),
         'separate reviewed old-API negative-control acceptance required')
    for path,h in baseline['proof_inputs'].items():
        need(plan['input_sha256'].get(path) == h, 'negative-control accepted evidence not pinned')
    need(read_json(HISTORICAL_P/'baseline-evidence/receipt.json')['complete'] is False and
         read_json(HISTORICAL_P/'baseline-control/receipt.json')['complete'] is False,
         'original failed baseline receipts must remain failed, never rewritten as success')
    return producer,qualification,controls


def build_commands(producer):
    # Derive only from the actual maintained successful first-four command rows.
    rows = read_json(P/'context-controls-revision1/receipt.json')['commands'][:4]
    old = P/'context-controls-revision1'
    replacements = {
      str(P/'tests-revision1/SourceContextCache.hs'):str(W/'FoundationStudy.hs'),
      str(old/'SourceContextCache.o'):str(BUILD/'FoundationStudy.o'),
      str(old/'SourceContextCache.hi'):str(BUILD/'FoundationStudy.hi'),
      str(old/'host.o'):str(BUILD/'host.o'),
      str(old/'supervisor.o'):str(BUILD/'supervisor.o'),
      str(old/'source-context-cache'):str(BUILD/'foundation-study')}
    expected_names = ['compile-fixture','compile-host','compile-supervisor','link-fixture']
    need([r['name'] for r in rows] == expected_names, 'maintained four-command population')
    result = []
    for row in rows:
        need(row['state'] == 'passed' and row['exit_code'] == 0 and
             row['timeout_seconds'] == 120 and row['cwd'] == str(S) and
             row['environment_overrides'] == {}, 'qualified maintained build row')
        result.append((row['name'],[replacements.get(token,token) for token in row['argv']],120))
    changed = {token for row in rows for token in row['argv'] if token in replacements}
    need(changed == set(replacements), 'exact six real path substitutions')
    need(result[0][1][-1] == str(W/'FoundationStudy.hs') and
         result[-1][1][-1] == str(BUILD/'foundation-study'), 'fixed helper target identity')
    # F.audit has independently compared these rows to maintained command construction.
    return result


def old_oracle_check(plan,L,I):
    expected = {str(OLD_PREFIX)+'.mlfci',str(OLD_PREFIX)+'.mlfco',
                str(OLD_BUILTIN)+'.mlfci',str(OLD_BUILTIN)+'.mlfco',str(OLD_INDEX)}
    inputs = plan['preflight_oracle_inputs']
    need(set(inputs) == expected, 'exact five old formal closure/index inputs')
    for path,item in inputs.items():
        q = Path(path)
        need(I.identity(q,digest=False) == {k:v for k,v in item.items() if k != 'sha256'},
             'old oracle input full stat changed: '+path)
        need(L.sha(q,16*MIB) == item['sha256'], 'old oracle input full SHA changed: '+path)
    # Pinned bytes plus explicit graph boundary: no arbitrary dependency reads.
    root = I.unpack(I.read_bounded(Path(str(OLD_PREFIX)+'.mlfci'),2*MIB).decode('utf-8'))
    builtin = I.unpack(I.read_bounded(Path(str(OLD_BUILTIN)+'.mlfci'),2*MIB).decode('utf-8'))
    need(len(root) == len(builtin) == 14 and root[0] == builtin[0] == 'MLFCI-5' and
         root[1] == 'mlf-foundation/0.3.0/library' and root[10] == builtin[10] == '' and
         builtin[1] == 'mlf:builtin-shared-haskell-v1:10' and I.unpack(builtin[2]) == [] and
         [I.unpack(row) for row in I.unpack(root[2])] ==
         [['mlf:builtin-shared-haskell-v1:10',str(OLD_BUILTIN)+'.mlfci','1553304259-2146574784']],
         'fixed actual two-crate formal dependency closure')
    return {'files':5,'full_sha_and_stat_verified':True,'cache_read':False,
            'old_measurement_reused':False}


def preflight_commands():
    return [(name,[str(BUILD/'foundation-study'),'--study-version',str(OLD_PREFIX),
                   str(OLD_INDEX),state,str(EV/(name+'.version'))],120,expected)
            for name,state,expected in [('version-original-control','original',0),
                                        ('version-mismatch-control','changed',1)]]


def audit_study(plan, runtime_sha, fixture_sha, L, I):
    out = W/'run'
    progress = read_json(out/'metadata/progress.json',2*MIB)
    need(progress['complete'] is True and progress['post_integrity'] is True and
         progress['error'] is None and progress['plan_sha256'] == runtime_sha and
         progress['fixture_sha256'] == fixture_sha and progress['stage_order'] == ORDER,
         'complete actual frozen study against exact runtime plan/binary')
    need(not (out/'entry-failure.json').exists(), 'inner entry failure retained: no qualification')
    stages,aux = progress['stages'],progress['auxiliary_commands']
    need([r['name'] for r in stages] == ORDER and len(aux) == 10,
         'ten fixed stages and ten untimed auxiliaries')
    cli = [name for name in ORDER if name != 'materializeB']
    need([r['name'] for r in aux] == ['prepare-builtin']+['version-'+name for name in cli],
         'one builtin and nine final/runtime audits')
    for row in stages+aux:
        need(row['state'] == 'passed' and row['exit_code'] == 0 and
             row['cwd'] == str(out) and row['argv'][0] == str(BUILD/'foundation-study') and
             row['timeout_seconds'] == 300, 'actual same-binary fixed command bounds')
        for kind in ('stdout','stderr'):
            q = Path(row[kind]['path'])
            need(q.is_relative_to(out) and I.identity(q) == {k:v for k,v in row[kind].items() if k != 'path'},
                 'complete retained command stream identity')
        need(row['stderr']['bytes'] == 0, 'unexpected study command stderr')
    need(sum(r['timed_endpoint'] is True for r in stages) == 9 and
         not any(r['timed_endpoint'] for r in aux), 'nine real CLI timing endpoints only')
    for row in stages:
        name = row['name']
        if name == 'materializeB':
            need(row['argv'][1] == '--study-materialize' and row['timed_endpoint'] is False,
                 'actual untimed legacy materializer')
            continue
        arm = 'A' if name.endswith('A') or name.startswith('warmA') else 'B'
        if name == 'coldA': arm = 'A'
        prefix = out/'outputs'/name/'unit'
        need(row['argv'] == [str(BUILD/'foundation-study'),'--compile-crate',
                            str(out/'metadata'/('crate-'+arm+'.spec')),'-o',str(prefix)],
             'ordinary public CLI exact spec/output identity')
        expect = (504,0) if name == 'coldA' else (1,503) if name in ('changeA','changeB') else (0,504)
        need(row['counts'] == dict(zip(('inferred','reused'),expect)), 'predeclared source counts')
        for suffix,artifact in row['artifacts'].items():
            q = Path(artifact['path'])
            need(str(q) == str(prefix)+suffix and
                 I.identity(q) == {k:v for k,v in artifact.items() if k != 'path'},
                 'complete raw/final/report bytes and stat retained')
        q = Path(row['snapshot_path'])
        need(L.sha(q,2*MIB) == row['snapshot_sha256'], 'complete cache snapshot retained')
    summary = json.loads(small(EV/'foundation-study.stdout',65536))
    need(summary == {'complete':True,'groups':504,'study_stages':10,
                     'real_cli_executions':9,'untimed_auxiliary_commands':10}, 'fixed inner completion summary')
    return {'progress_sha256':L.sha(out/'metadata/progress.json',2*MIB),
            'groups':504,'stages':10,'real_cli':9,'auxiliary':10,
            'interpretation':'One same-binary real-source comparison; no causal/statistical compiler speedup claim.'}


def save(record, first=False):
    raw = (json.dumps(record,indent=2)+'\n').encode()
    need(len(raw) <= 2*MIB, 'outer receipt bound')
    with (EV/'receipt.json').open('xb' if first else 'wb') as stream:
        stream.write(raw)


class GuardReceiptSnapshotRace(RuntimeError):
    def __init__(self, temporary, attempts):
        self.temporary = str(temporary)
        self.attempts = attempts
        super().__init__("guard receipt snapshot race exhausted: attempts=" +
                         str(attempts) + "; path=" + str(temporary))


def snapshot_with_guard_retry(sample, guard_directory):
    """Return one complete sample; retry ONLY the exact active tmp ENOENT.

    Three attempts include the first attempt. A partial account is discarded,
    never returned or carried into the next account. Non-racing initial samples
    need not wait for the parent's first receipt save after Popen.
    """
    guard = Path(guard_directory)
    if not guard.is_absolute() or guard != W / 'guard':
        raise RuntimeError('fixed absolute active guard directory required')

    def directory_identity():
        info = guard.lstat()
        if not stat.S_ISDIR(info.st_mode) or guard.resolve(strict=True) != guard:
            raise RuntimeError('guard directory is not a canonical real directory')
        return info.st_dev, info.st_ino

    initial = directory_identity()
    fd = os.open(guard, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = guard / 'bounded-receipt.json.tmp'
    observations = []

    def validate_directory():
        held = os.fstat(fd)
        if (not stat.S_ISDIR(held.st_mode) or
                (held.st_dev, held.st_ino) != initial or
                directory_identity() != initial):
            raise RuntimeError('active guard directory identity changed')

    def observe_renamed_receipt():
        info = os.stat('bounded-receipt.json', dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError('guard receipt is not a single-link regular file')
        return {'device': info.st_dev, 'inode': info.st_ino,
                'bytes': info.st_size, 'allocated': info.st_blocks * 512,
                'mode': info.st_mode, 'links': info.st_nlink,
                'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}

    try:
        for attempt in range(1, 4):
            validate_directory()
            try:
                value = sample()
            except FileNotFoundError as error:
                if (error.errno != errno.ENOENT or
                        error.filename != str(temporary) or
                        error.filename2 is not None):
                    raise
                validate_directory()
                # A legitimate rename has produced the final receipt. Missing,
                # directory, symlink or multi-link final entries fail here.
                observations.append(observe_renamed_receipt())
                validate_directory()
                if attempt == 3:
                    raise GuardReceiptSnapshotRace(temporary, attempt) from error
                continue
            validate_directory()
            if type(value) is not dict or 'guard_receipt_resampling' in value:
                raise RuntimeError('unexpected budget sample result schema')
            return {**value, 'guard_receipt_resampling': {
                'attempts': attempt, 'restarts': attempt - 1,
                'temporary_path': str(temporary),
                'observed_final_receipts_after_tmp_enoent': observations,
                'scope': 'complete sampled account; not atomic or hard isolation'}}
        raise AssertionError('unreachable bounded sampling loop')
    finally:
        os.close(fd)


def terminal_sample(L,I):
    # Called only AFTER current terminal receipt/progress/entry-failure writes.
    root = snapshot_with_guard_retry(L.root_budget_raw, W / "guard")
    need(max(root['logical'],root['pathname_allocated']) <= 8192*MIB, 'post-receipt ROOT account')
    return {'root':root,'whole_work':I.budget_snapshot(W/'run'),
            'scope':'after inner terminal files and outer receipt; later stdout/guard writes excluded; original guard continues sampled monitoring'}


def main():
    need(len(sys.argv) == 2 and SHA.fullmatch(sys.argv[1]) is not None, 'exact final-plan SHA argument')
    raw = small(FINAL,64*1024)
    need(digest(raw) == sys.argv[1], 'exact reviewed final-plan hash')
    plan = json.loads(raw,object_pairs_hook=unique)
    # Reject before loading helpers or creating runtime evidence/private directories.
    need(plan.get('approved_for_execution') is True and plan.get('resource_protocol_accepted') is True,
         'draft has no resource/execution admission')
    need(plan.get('other_root_authors_paused') is True and plan.get('limits') == LIMITS and
         plan.get('reservation_bytes') == 448*MIB and plan.get('tail_metadata_reserve_bytes') == 2*MIB and
         plan.get('whole_study_seconds') == 900 and plan.get('build_command_seconds') == 120,
         'fixed reviewed resource protocol')
    need(plan.get('root') == str(R) and plan.get('work') == str(W) and
         plan.get('producer') == str(PRODUCER) and plan.get('source_root') == str(S), 'fixed real roots')
    need(isinstance(plan.get('producer_state'),dict) and
         set(plan['producer_state']) == {'receipt_sha256','closed_tree_sha256'} and
         all(isinstance(v,str) and SHA.fullmatch(v) for v in plan['producer_state'].values()),
         'actual current producer state required, never draft/M qualification')
    pins = plan['input_sha256']
    need(pins and all(isinstance(h,str) and SHA.fullmatch(h) for h in pins.values()), 'no pending input pins')
    need(all(pins.get(path) == h for path,h in FIXED.items()), 'frozen six study/current helper pins')
    need(digest(small(Path(__file__).absolute(),48*1024)) == plan['launcher_sha256'], 'launcher bytes')
    need(plan['guard_argv'] == guard_argv('<plan-sha256>'), 'unchanged original guard invocation')
    L,bp,F,I = support(plan)
    lock = R/'.reproduction.lock'
    initial = L.regular(lock)
    fd = os.open(lock,os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        held = os.fstat(fd)
        need((held.st_dev,held.st_ino) == tuple(initial[:2]) and
             L.regular(lock)[:2] == initial[:2], 'stable child reproduction lock fd/path')
        pin_check(plan,L,bp)
        producer,qualification,controls = prerequisites(plan,L,bp,F)
        template = read_json(TEMPLATE,32*1024)
        need(template['approved_for_execution'] is False and template['resource_protocol_accepted'] is False and
             template['producer_state'] is None and template['stage_order'] == ORDER,
             'unchanged unexecuted frozen template')
        for row in template['source_inputs']:
            need(bp['source_sha256'][row['relative']] == row['sha256'], 'current foundation source matches historical14')
        admission = snapshot_with_guard_retry(L.root_budget_raw, W / "guard")
        need(max(admission['logical'],admission['pathname_allocated'])+450*MIB <= 8192*MIB,
             'fresh actual ROOT plus448reservation plus2tail exceeds original8GiB')
        I.budget_snapshot(W/'run')
        for q in [EV,BUILD,W/'run',*PRIVATE]:
            need(not q.exists() and not q.is_symlink(), 'fresh output required, retain prior failures: '+str(q))
        for q in [EV,BUILD,*PRIVATE]: q.mkdir()
        record = {'format':'foundation-current-qualified-v1','complete':False,'phase':'build',
                  'plan_sha256':sys.argv[1],'producer_state':plan['producer_state'],
                  'producer_authentication':qualification,'prior40R1':controls,'commands':[],
                  'environment':environment(),'admission':admission,'error':None,
                  'terminal_qualification_requires_stdout_and_successful_original_guard':True,
                  'interpretation':'L current186/255; source504 not synthetic64; no producer/native/performance claim beyond recorded checks.'}
        save(record,True)
        error = None
        fixture_sha = runtime_sha = None
        def run(name,command,timeout,expected_exit=0):
            row = {'name':name,'argv':command,'cwd':str(S),'timeout_seconds':timeout,'expected_exit_code':expected_exit,'state':'running',
                   'budget_before':I.budget_snapshot(W/'run')}
            record['commands'].append(row);save(record)
            start = time.monotonic()
            try:
                with (EV/(name+'.stdout')).open('xb') as out, (EV/(name+'.stderr')).open('xb') as err:
                    child = subprocess.run(command,cwd=S,env=environment(),stdin=subprocess.DEVNULL,
                                           stdout=out,stderr=err,timeout=timeout,check=False)
                row['exit_code'] = child.returncode
            finally:
                row['wall_seconds_to_child_exit'] = time.monotonic()-start
                row['state'] = 'exited-not-qualified'
                for kind in ('stdout','stderr'):
                    q = EV/(name+'.'+kind)
                    if q.exists(): row[kind] = {'path':str(q),'bytes':q.stat().st_size,'sha256':L.sha(q,2*MIB)}
                save(record)
            if expected_exit == 1:
                need(name == 'version-mismatch-control' and row['exit_code'] == 1 and
                     small(EV/(name+'.stdout'),65536) == b'' and
                     small(EV/(name+'.stderr'),65536) == NEGATIVE_STDERR and
                     not (EV/(name+'.version')).exists() and not (EV/(name+'.version')).is_symlink(),
                     'negative control must reach exact expected0.3.1/actual0.3.0 mismatch, not arbitrary failure')
            else:
                need(expected_exit == 0 and row['exit_code'] == 0 and row['stderr']['bytes'] == 0,
                     'command failed: '+name)
            row['budget_after'] = I.budget_snapshot(W/'run')
            pin_check(plan,L,bp)
            row['state'] = 'passed';save(record)
        try:
            for name,command,timeout in build_commands(producer): run(name,command,timeout)
            expected = {'FoundationStudy.o','FoundationStudy.hi','host.o','supervisor.o','foundation-study'}
            need({q.name for q in BUILD.iterdir()} == expected, 'exact helper artifacts, no source/object copy')
            record['helper_artifacts'] = {str(q):L.sha(q,32*MIB) for q in sorted(BUILD.iterdir())}
            fixture_sha = record['helper_artifacts'][str(BUILD/'foundation-study')]
            record['phase'] = 'old-final-oracle-prerequisites';save(record)
            record['old_oracle_inputs_before'] = old_oracle_check(plan,L,I)
            for name,command,timeout,expected_exit in preflight_commands():
                evidence = EV/(name+'.version')
                need(not evidence.exists() and not evidence.is_symlink(), 'fresh preflight evidence')
                run(name,command,timeout,expected_exit)
                if expected_exit == 0:
                    need(small(EV/(name+'.stdout'),65536) == POSITIVE_STDOUT and
                         I.unpack(small(evidence,4096).decode('utf-8')) ==
                         ['MLF-FOUNDATION-VERSION-1','504','0.3.0'], 'original old-final exact RString control')
                    record['positive_preflight_evidence'] = {'path':str(evidence),**I.identity(evidence)}
                record[name+'_old_inputs_after'] = old_oracle_check(plan,L,I)
                save(record)
            runtime = template.copy()
            runtime.update(approved_for_execution=True,resource_protocol_accepted=True,
                source_root=str(S),producer=str(PRODUCER),producer_state=plan['producer_state'],
                fixture=str(BUILD/'foundation-study'),fixture_sha256=fixture_sha,
                runner_sha256=FIXED[str(IR)],qualified_outer_launcher={
                    'path':str(Path(__file__).absolute()),'sha256':plan['launcher_sha256'],
                    'plan_sha256':sys.argv[1],'original_guard':str(R/'run-guarded.sh')},
                pinned_inputs={**pins,**{str(S/rel):h for rel,h in bp['source_sha256'].items()},
                               str(PRODUCER/'receipt.json'):plan['producer_state']['receipt_sha256']})
            runtime['resource_protocol'] = {**runtime['resource_protocol'],'tail_metadata_reserve_bytes':2*MIB}
            runtime['intended_current_source'] = plan['actual_current_source']
            runtime_path = EV/'study-plan.json'
            runtime_raw = (json.dumps(runtime,indent=2)+'\n').encode()
            need(len(runtime_raw) <= 256*1024, 'runtime plan metadata bound')
            with runtime_path.open('xb') as stream: stream.write(runtime_raw)
            runtime_sha = digest(runtime_raw)
            record['runtime_plan_sha256'] = runtime_sha;record['fixture_sha256'] = fixture_sha
            record['phase'] = 'real-source-study';save(record)
            run('foundation-study',[PYTHON,'-I','-B',str(IR),'--plan',str(runtime_path),
                                    '--plan-sha256',runtime_sha],900)
            record['study'] = audit_study(plan,runtime_sha,fixture_sha,L,I)
            need(all(L.sha(Path(q),32*MIB) == h for q,h in record['helper_artifacts'].items()),
                 'same helper artifacts after complete study')
        except BaseException as exc:
            error = type(exc).__name__+': '+str(exc)
        finally:
            try:
                pin_check(plan,L,bp)
                record['post_producer_authentication'] = L.audit_producer(bp)
                record['post_old_oracle_inputs'] = old_oracle_check(plan,L,I)
                if 'positive_preflight_evidence' in record:
                    item = record['positive_preflight_evidence']
                    need(I.identity(Path(item['path'])) == {k:v for k,v in item.items() if k != 'path'},
                         'retained positive preflight evidence changed')
                need(L.regular(lock)[:2] == initial[:2], 'unchanged coordination lock pathname')
                record['post_inputs_producer_unchanged'] = True
                record['budget_before_outer_terminal_receipt'] = terminal_sample(L,I)
            except BaseException as exc:
                error = (error+'; ' if error else '')+'postcheck: '+type(exc).__name__+': '+str(exc)
                record['post_inputs_producer_unchanged'] = False
            record['error'] = error
            record['complete'] = error is None and len(record['commands']) == 7 and 'study' in record
            record['phase'] = 'complete-pending-post-receipt-account' if record['complete'] else 'failed'
            save(record)
            try:
                terminal = terminal_sample(L,I)
            except BaseException as exc:
                record['complete'] = False
                record['error'] = (record['error']+'; ' if record['error'] else '')+'terminal-account: '+str(exc)
                record['phase'] = 'failed';save(record)
                try: terminal = terminal_sample(L,I)
                except BaseException as again: terminal = {'error':str(again),'complete':False}
            # This is the final account AFTER the saved outer receipt, not an earlier snapshot.
            print(json.dumps({'terminal_post_receipt_account':terminal,'complete':record['complete'],
                              'receipt_sha256':L.sha(EV/'receipt.json',2*MIB)}),flush=True)
        need(record['complete'],record['error'] or 'qualification incomplete')
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
