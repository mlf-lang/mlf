#!/usr/bin/env python3
"""Verify full history and execute preparation routing before its consumers."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import history_refs as history
from workflow_yaml import load

ROOT = Path(__file__).resolve().parents[2]
WRAPPED_BY_RELEASE_CHECK = {('ci', 'metadata')}
CALLERS = {
    'ci': ('metadata', 'native'),
    'native-qualification': ('metadata', 'mac-package', 'linux-package'),
    'platform-release': ('metadata',),
    'recover-release': ('metadata', 'macos-package'),
}
PREPARE = 'tools/testing/prepare_history_refs.py'


def command_step(job, command):
    matches = [step for step in job['steps'] if command in step.get('run', '')]
    if len(matches) != 1:
        raise ValueError('expected one command step: ' + command)
    return matches[0]


def check_run(script, *, release=False, fail=False, present=True):
    """Run actual shell control flow with a Python stand-in and private files."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'tools/testing').mkdir(parents=True)
        if present:
            (root / PREPARE).touch()
        if release:
            # check.sh resolves its root using $0; reproduce that layout.
            (root / 'tools/release').mkdir()
        prelude = r'''
python3() {
  printf '%s\n' "$*"
  case " $* " in
    *' tools/testing/prepare_history_refs.py '*) return "$PREPARE_STATUS" ;;
    *' tools/testing/run.py benchmark-provenance '*) exit 0 ;;
  esac
}
'''
        shell = ['/bin/bash', '--noprofile', '--norc']
        if not release:
            shell += ['-e']
        result = subprocess.run([*shell, '-c', prelude + script, str(root / 'tools/release/check.sh')],
                                cwd=root, env={'PATH': '/usr/bin:/bin', 'PREPARE_STATUS': '73' if fail else '0'},
                                text=True, capture_output=True, timeout=5)
        calls = [line.split() for line in result.stdout.splitlines()]
        expected_prepare = ['-B', PREPARE]
        if not present:
            if result.returncode or calls:
                raise ValueError('old recovery sources must not invoke a missing history helper')
        elif fail:
            if result.returncode != 73 or not calls or calls[-1] != expected_prepare:
                raise ValueError('failed preparation must stop validation')
        elif release:
            expected = [['-B', 'tools/testing/run.py', suite]
                        for suite in ['release-metadata', 'release-metadata-diff']]
            expected += [expected_prepare, ['-B', 'tools/testing/run.py', 'benchmark-provenance']]
            if result.returncode or calls != expected:
                raise ValueError('release wrapper must prepare history before its consumers')
        elif result.returncode or calls != [expected_prepare]:
            raise ValueError('history preparation must execute exactly once')


def check_release_entry(script):
    """The metadata job must really invoke, and propagate, its release wrapper."""
    for status in [0, 73]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrapper = root / 'tools/release/check.sh'
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text('#!/bin/bash\nprintf 1 >> "$WRAPPER_TRACE"\nexit "$WRAPPER_STATUS"\n')
            wrapper.chmod(0o755)
            trace = root / 'calls'
            result = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-e', '-c', script],
                                    cwd=root, env={'PATH': '/usr/bin:/bin', 'WRAPPER_TRACE': str(trace),
                                                   'WRAPPER_STATUS': str(status)},
                                    text=True, capture_output=True, timeout=5)
            if result.returncode != status or not trace.is_file() or trace.read_text() != '1':
                raise ValueError('metadata must execute its release wrapper and propagate failure')


def release_fixture(preparation, *, after=False):
    # Independent shell fixture: the actual wrapper is executed by the positive
    # contract. Negative cases need not know its helper names or source layout.
    metadata = ''.join('python3 -B tools/testing/run.py ' + suite + '\n'
                       for suite in ['release-metadata', 'release-metadata-diff'])
    consumer = 'python3 -B tools/testing/run.py benchmark-provenance\n'
    return 'set -euo pipefail\n' + metadata + (consumer + preparation if after else preparation + '\n' + consumer)


def require_callers(workflows, release_check):
    for name, consumers in CALLERS.items():
        for consumer in consumers:
            job = workflows[name]['jobs'].get(consumer)
            if job is None:
                raise ValueError('missing history consumer: ' + name + '/' + consumer)
            steps = job['steps']
            checkouts = [step for step in steps if step.get('uses', '').split('@')[0] == 'actions/checkout'
                         and not step.get('with', {}).get('path')]
            if len(checkouts) != 1 or str(checkouts[0].get('with', {}).get('fetch-depth')) != '0':
                raise ValueError('consumer requires full source history: ' + consumer)
            if checkouts[0].get('if') not in (None, True) or checkouts[0].get('continue-on-error'):
                raise ValueError('source checkout must not be suppressed')
            command = ('--bootstrap-only' if name == 'ci' and consumer == 'native' else
                       'tools/release/check.sh' if consumer == 'metadata' else 'tools/release/package.sh')
            validation = command_step(job, command)
            if (name, consumer) in WRAPPED_BY_RELEASE_CHECK:
                if validation.get('if') not in (None, True) or validation.get('continue-on-error'):
                    raise ValueError('history validation requires the unsuppressed release wrapper')
                if steps.index(checkouts[0]) >= steps.index(validation):
                    raise ValueError('checkout must precede release validation')
                check_release_entry(validation['run'])
                check_run(release_check, release=True)
                check_run(release_check, release=True, fail=True)
                continue
            preparation = command_step(job, PREPARE)
            if preparation.get('if') not in (None, True) or preparation.get('continue-on-error'):
                raise ValueError('history preparation must not be suppressed')
            if not steps.index(checkouts[0]) < steps.index(preparation) < steps.index(validation):
                raise ValueError('history preparation must precede validation: ' + consumer)
            check_run(preparation['run'])
            check_run(preparation['run'], fail=True)
            if name == 'recover-release':
                check_run(preparation['run'], present=False)


class HistoryWorkflowControls(unittest.TestCase):
    def setUp(self):
        self.workflows = {name: load((ROOT / '.github/workflows' / (name + '.yml')).read_text())
                          for name in CALLERS}
        self.release_check = (ROOT / 'tools/release/check.sh').read_text()

    def test_all_validation_and_packaging_consumers_prepare_history(self):
        require_callers(self.workflows, self.release_check)

    def test_yaml_reformat_step_names_and_shell_locals_do_not_change_history(self):
        changed = copy.deepcopy(self.workflows)
        for workflow in changed.values():
            for job in workflow['jobs'].values():
                for step in job.get('steps', []):
                    if 'name' in step:
                        step['name'] = 'A different display name'
                    if PREPARE in step.get('run', ''):
                        step['run'] = '# Source presentation is not a contract\n' + step['run']
        # JSON is also YAML; quoted keys and flow collections are equivalent.
        changed = {name: load(json.dumps(value, sort_keys=True, indent=4))
                   for name, value in changed.items()}
        require_callers(changed, self.release_check.replace(
            'python3 -B ' + PREPARE, 'history_helper=' + PREPARE + '\npython3 -B "$history_helper"'))

    def test_each_missing_or_suppressed_preparation_is_rejected(self):
        for name, jobs in CALLERS.items():
            for job in jobs:
                if (name, job) in WRAPPED_BY_RELEASE_CHECK:
                    continue
                for mutation in ['remove', 'comment', 'condition', 'failure']:
                    with self.subTest(workflow=name, job=job, mutation=mutation):
                        changed = copy.deepcopy(self.workflows)
                        owner = changed[name]['jobs'][job]
                        step = command_step(owner, PREPARE)
                        if mutation == 'remove':
                            owner['steps'].remove(step)
                        elif mutation == 'comment':
                            step['run'] = '\n'.join('# ' + line for line in step['run'].splitlines())
                        elif mutation == 'condition':
                            step['if'] = False
                        else:
                            step['continue-on-error'] = True
                        with self.assertRaises(ValueError):
                            require_callers(changed, self.release_check)

    def test_release_wrapper_preparation_cannot_be_missing_or_suppressed(self):
        command = 'python3 -B ' + PREPARE
        fixture = release_fixture(command)
        require_callers(self.workflows, fixture)
        with self.assertRaises(ValueError):
            require_callers(self.workflows, fixture.replace('set -euo pipefail', 'set -u -o pipefail'))
        for replacement in ('', 'echo ' + command, command + ' || true'):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                require_callers(self.workflows, release_fixture(replacement))
        for body in ['# tools/release/check.sh', 'tools/release/check.sh || true']:
            changed = copy.deepcopy(self.workflows)
            command_step(changed['ci']['jobs']['metadata'], 'tools/release/check.sh')['run'] = body
            with self.subTest(wrapper=body), self.assertRaises(ValueError):
                require_callers(changed, self.release_check)
        changed = copy.deepcopy(self.workflows)
        command_step(changed['ci']['jobs']['metadata'], 'tools/release/check.sh')['if'] = False
        with self.assertRaises(ValueError):
            require_callers(changed, self.release_check)

    def test_each_shallow_source_checkout_is_rejected(self):
        for name, jobs in CALLERS.items():
            for job in jobs:
                with self.subTest(workflow=name, job=job):
                    changed = copy.deepcopy(self.workflows)
                    checkout = next(step for step in changed[name]['jobs'][job]['steps']
                                    if step.get('uses', '').startswith('actions/checkout@'))
                    checkout['with']['fetch-depth'] = 1
                    with self.assertRaises(ValueError):
                        require_callers(changed, self.release_check)

    def test_preparation_after_validation_is_rejected(self):
        command = 'python3 -B ' + PREPARE
        moved = release_fixture(command, after=True)
        with self.assertRaises(ValueError):
            require_callers(self.workflows, moved)
        changed = copy.deepcopy(self.workflows)
        steps = changed['ci']['jobs']['native']['steps']
        step = command_step(changed['ci']['jobs']['native'], PREPARE)
        steps.remove(step)
        steps.append(step)
        with self.assertRaises(ValueError):
            require_callers(changed, self.release_check)

    def test_pr19_historical_reconciliation_inputs_remain_independently_pinned(self):
        for path in history.RECONCILED_MAIN_PATHS:
            with self.subTest(path=path):
                frozen = history.historical_bytes('4d732f31982ebe18124511f2ca4cb412770d6bd6', path)
                digest = hashlib.sha256(frozen).hexdigest()
                current = history._git('show', 'afbe7219806881301831d79f43596811eca3279d:' + path)
                self.assertTrue(history.checked_current(path, current, digest))
                self.assertFalse(history.checked_current(path, current + b'\n# unauthorized delta\n', digest))
                with self.assertRaisesRegex(ValueError, 'frozen reconciliation input changed'):
                    history.checked_current(path, current, '0' * 64)

    def test_duplicate_yaml_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate workflow key'):
            load('on: {push: {}}\njobs: {}\njobs: {other: {}}\n')


if __name__ == '__main__':
    unittest.main()
