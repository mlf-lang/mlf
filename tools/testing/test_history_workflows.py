#!/usr/bin/env python3
"""Keep full-history preparation before every metadata/SDK validation caller."""
import hashlib
from pathlib import Path
import re
import unittest

import history_refs as history

ROOT = Path(__file__).resolve().parents[2]
RELEASE_ENTRY = '      - run: tools/release/check.sh'
RELEASE_PREPARE = 'python3 -B tools/testing/prepare_history_refs.py'
FIRST_HISTORY_SUITE = 'run benchmark-provenance'
WRAPPED_BY_RELEASE_CHECK = {('ci', 'metadata')}
CALLERS = {
    'ci': ('metadata', 'native'),
    'native-qualification': ('metadata', 'mac-package', 'linux-package'),
    'platform-release': ('metadata',),
    'recover-release': ('metadata', 'macos-package'),
}
PREPARE = (
    '      - name: Prepare reviewed historical source objects\n'
    '        run: python3 -B tools/testing/prepare_history_refs.py\n'
)
# Recovery can select a source predating the history audit. Its original
# check.sh remains authoritative; no missing helper is tolerated by new sources.
RECOVERY_PREPARE = (
    '      - name: Prepare reviewed historical source objects when required by the selected source\n'
    '        run: |\n'
    '          if test -f tools/testing/prepare_history_refs.py; then\n'
    '            python3 -B tools/testing/prepare_history_refs.py\n'
    '          fi\n'
)


def require_callers(workflows, release_check):
    for workflow, jobs in CALLERS.items():
        for job in jobs:
            match = re.search(r'^  ' + re.escape(job) + r':\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)',
                              workflows[workflow], re.M | re.S)
            if match is None:
                raise ValueError('missing history consumer: ' + workflow + '/' + job)
            body = match[1]
            steps = re.findall(r'^      - .*?(?=^      - |\Z)', body, re.M | re.S)
            checkouts = [step for step in steps if step.startswith('      - uses: actions/checkout@')]
            if not checkouts or len(re.findall(r'^          fetch-depth: 0(?:[ \t]+#[^\n]*)?$', checkouts[0], re.M)) != 1:
                raise ValueError('consumer requires full source history: ' + job)
            if (workflow, job) in WRAPPED_BY_RELEASE_CHECK:
                matching = [step for step in steps if step.rstrip() == RELEASE_ENTRY]
                if len(matching) != 1 or body.index(checkouts[0]) >= body.index(RELEASE_ENTRY):
                    raise ValueError('history validation requires the unsuppressed release wrapper: ' + job)
                lines = release_check.splitlines()
                if (lines.count(RELEASE_PREPARE) != 1 or FIRST_HISTORY_SUITE not in lines
                        or 'set -euo pipefail' not in lines
                        or not (lines.index('set -euo pipefail') < lines.index(RELEASE_PREPARE)
                                < lines.index(FIRST_HISTORY_SUITE))):
                    raise ValueError('release wrapper must prepare history before its consumers')
                continue
            expected = RECOVERY_PREPARE if workflow == 'recover-release' else PREPARE
            matching = [step for step in steps if step.rstrip() == expected.rstrip()]
            if len(matching) != 1:
                raise ValueError('consumer requires exact unsuppressed preparation: ' + job)
            command = ('tools/shared/build.py' if workflow == 'ci' and job == 'native' else
                       'tools/release/check.sh' if job == 'metadata' else 'tools/release/package.sh')
            if command not in body or not (body.index(checkouts[0]) < body.index(expected) < body.index(command)):
                raise ValueError('history preparation must precede validation: ' + job)


class HistoryWorkflowControls(unittest.TestCase):
    def setUp(self):
        self.workflows = {name: (ROOT / '.github/workflows' / (name + '.yml')).read_text()
                          for name in CALLERS}
        self.release_check = (ROOT / 'tools/release/check.sh').read_text()

    def test_all_validation_and_packaging_consumers_prepare_history(self):
        require_callers(self.workflows, self.release_check)

    def test_each_missing_or_suppressed_preparation_is_rejected(self):
        for name, jobs in CALLERS.items():
            explicit_jobs = [job for job in jobs if (name, job) not in WRAPPED_BY_RELEASE_CHECK]
            expected = RECOVERY_PREPARE if name == 'recover-release' else PREPARE
            for index, job in enumerate(explicit_jobs):
                offsets = [match.start() for match in re.finditer(re.escape(expected), self.workflows[name])]
                self.assertEqual(len(offsets), len(explicit_jobs))
                offset = offsets[index]
                for replacement in ('', expected.replace('python3 -B', 'echo python3 -B'),
                                    expected.replace('        run:', '        if: false\n        run:'),
                                    expected + '        continue-on-error: true\n'):
                    with self.subTest(workflow=name, job=job, replacement=replacement):
                        changed = dict(self.workflows)
                        changed[name] = changed[name][:offset] + replacement + changed[name][offset + len(expected):]
                        with self.assertRaises(ValueError):
                            require_callers(changed, self.release_check)

    def test_release_wrapper_preparation_cannot_be_missing_or_suppressed(self):
        for replacement in ('', 'echo ' + RELEASE_PREPARE, RELEASE_PREPARE + ' || true'):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                require_callers(self.workflows, self.release_check.replace(RELEASE_PREPARE, replacement))
        removed = dict(self.workflows)
        removed['ci'] = removed['ci'].replace(RELEASE_ENTRY, RELEASE_ENTRY + '\n        if: false', 1)
        with self.assertRaises(ValueError):
            require_callers(removed, self.release_check)

    def test_each_shallow_source_checkout_is_rejected(self):
        for name, jobs in CALLERS.items():
            for job in jobs:
                with self.subTest(workflow=name, job=job):
                    changed = dict(self.workflows)
                    start = changed[name].index('  ' + job + ':\n')
                    offset = changed[name].index('          fetch-depth: 0', start)
                    changed[name] = changed[name][:offset] + changed[name][offset:].replace('fetch-depth: 0', 'fetch-depth: 1', 1)
                    with self.assertRaises(ValueError):
                        require_callers(changed, self.release_check)

    def test_preparation_after_validation_is_rejected(self):
        moved = self.release_check.replace(RELEASE_PREPARE + '\n', '', 1).replace(
            FIRST_HISTORY_SUITE, FIRST_HISTORY_SUITE + '\n' + RELEASE_PREPARE, 1)
        with self.assertRaises(ValueError):
            require_callers(self.workflows, moved)
        changed = dict(self.workflows)
        changed['ci'] = changed['ci'].replace(PREPARE, '', 1).replace(
            '      - name: Preserve actual builtin generation after freshness failure\n',
            PREPARE + '      - name: Preserve actual builtin generation after freshness failure\n', 1)
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


if __name__ == '__main__':
    unittest.main()
