#!/usr/bin/env python3
"""Keep full-history preparation before every metadata/SDK validation caller."""
import hashlib
from pathlib import Path
import re
import unittest

import history_refs as history

ROOT = Path(__file__).resolve().parents[2]
CALLERS = {
    'ci': ('metadata',),
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


def require_callers(workflows):
    for workflow, jobs in CALLERS.items():
        for job in jobs:
            match = re.search(r'^  ' + re.escape(job) + r':\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)',
                              workflows[workflow], re.M | re.S)
            if match is None:
                raise ValueError('missing history consumer: ' + workflow + '/' + job)
            body = match[1]
            steps = re.findall(r'^      - .*?(?=^      - |\Z)', body, re.M | re.S)
            checkouts = [step for step in steps if step.startswith('      - uses: actions/checkout@')]
            if not checkouts or len(re.findall(r'^          fetch-depth: 0$', checkouts[0], re.M)) != 1:
                raise ValueError('consumer requires full source history: ' + job)
            expected = RECOVERY_PREPARE if workflow == 'recover-release' else PREPARE
            matching = [step for step in steps if step.rstrip() == expected.rstrip()]
            if len(matching) != 1:
                raise ValueError('consumer requires exact unsuppressed preparation: ' + job)
            command = 'tools/release/check.sh' if job == 'metadata' else 'tools/release/package.sh'
            if command not in body or not (body.index(checkouts[0]) < body.index(expected) < body.index(command)):
                raise ValueError('history preparation must precede validation: ' + job)


class HistoryWorkflowControls(unittest.TestCase):
    def setUp(self):
        self.workflows = {name: (ROOT / '.github/workflows' / (name + '.yml')).read_text()
                          for name in CALLERS}

    def test_all_validation_and_packaging_consumers_prepare_history(self):
        require_callers(self.workflows)

    def test_each_missing_or_suppressed_preparation_is_rejected(self):
        for name, jobs in CALLERS.items():
            expected = RECOVERY_PREPARE if name == 'recover-release' else PREPARE
            for index, _job in enumerate(jobs):
                offsets = [match.start() for match in re.finditer(re.escape(expected), self.workflows[name])]
                self.assertEqual(len(offsets), len(jobs))
                offset = offsets[index]
                for replacement in ('', expected.replace('python3 -B', 'echo python3 -B'),
                                    expected.replace('        run:', '        if: false\n        run:'),
                                    expected + '        continue-on-error: true\n'):
                    with self.subTest(workflow=name, job=_job, replacement=replacement):
                        changed = dict(self.workflows)
                        changed[name] = changed[name][:offset] + replacement + changed[name][offset + len(expected):]
                        with self.assertRaises(ValueError):
                            require_callers(changed)

    def test_each_shallow_source_checkout_is_rejected(self):
        for name, jobs in CALLERS.items():
            for job in jobs:
                with self.subTest(workflow=name, job=job):
                    changed = dict(self.workflows)
                    start = changed[name].index('  ' + job + ':\n')
                    offset = changed[name].index('          fetch-depth: 0', start)
                    changed[name] = changed[name][:offset] + changed[name][offset:].replace('fetch-depth: 0', 'fetch-depth: 1', 1)
                    with self.assertRaises(ValueError):
                        require_callers(changed)

    def test_preparation_after_validation_is_rejected(self):
        changed = dict(self.workflows)
        changed['ci'] = changed['ci'].replace(PREPARE, '', 1).replace(
            '      - run: tools/release/check.sh\n', '      - run: tools/release/check.sh\n' + PREPARE, 1)
        with self.assertRaises(ValueError):
            require_callers(changed)

    def test_incoming_main_and_frozen_inputs_are_independently_pinned(self):
        for path in history.RECONCILED_MAIN_PATHS:
            with self.subTest(path=path):
                frozen = history.historical_bytes('4d732f31982ebe18124511f2ca4cb412770d6bd6', path)
                digest = hashlib.sha256(frozen).hexdigest()
                current = (ROOT / path).read_bytes()
                self.assertTrue(history.checked_current(path, current, digest))
                self.assertFalse(history.checked_current(path, current + b'\n# unauthorized delta\n', digest))
                with self.assertRaisesRegex(ValueError, 'frozen reconciliation input changed'):
                    history.checked_current(path, current, '0' * 64)


if __name__ == '__main__':
    unittest.main()
