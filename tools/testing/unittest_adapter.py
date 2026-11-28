"""Report each actual unittest result while preserving discovery and fixtures."""

import os
import runpy
from pathlib import Path
import sys
import unittest

import events


def leaves(suite):
    if isinstance(suite, unittest.TestSuite):
        for entry in suite:
            yield from leaves(entry)
    else:
        yield suite


def case_id(test):
    label = test.id().removeprefix("__main__.")
    return os.environ["MLF_TEST_ID_PREFIX"] + label


def selected_suite(suite, exact):
    if isinstance(suite, unittest.TestSuite):
        entries = [selected for entry in suite
                   if (selected := selected_suite(entry, exact)) is not None]
        return type(suite)(entries) if entries else None
    return suite if case_id(suite) == exact else None


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        self.observed = {}

    def startTest(self, test):
        super().startTest(test)
        events.start(case_id(test))

    def stopTest(self, test):
        super().stopTest(test)
        outcome = self.observed.pop(test, None)
        if outcome is not None:
            status, detail = outcome
            events.result(case_id(test), status, detail=detail)

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "pass", "")

    def _record(self, test, status, detail):
        if isinstance(test, unittest.TestCase):
            previous = self.observed.get(test)
            if previous is None:
                self.observed[test] = status, detail
            elif status == "fail":
                details = [value for value in (previous[1], detail) if value]
                self.observed[test] = status, "\n".join(details)
        else:
            # Failed setUpClass/setUpModule/tearDown hooks also affect the
            # process exit and are never substituted for scheduled cases.
            print(f"test fixture {test}: {detail}", file=sys.stderr)

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "fail", self._exc_info_to_string(err, test))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "fail", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(getattr(test, "test_case", test), "skip", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record(test, "pass", "expected failure: " + self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, "fail", "unexpected success")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._record(test, "fail", self._exc_info_to_string(err, subtest))


class EvidenceRunner(unittest.TextTestRunner):
    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        self.resultclass = EvidenceResult

    def run(self, suite):
        ids = [case_id(test) for test in leaves(suite)]
        exact = os.environ.get("MLF_TEST_EXACT")
        if exact:
            suite = selected_suite(suite, exact)
            if suite is None:
                raise SystemExit(f"unknown case: {exact}")
            ids = [exact]
        if not ids or len(ids) != len(set(ids)):
            raise SystemExit("empty or duplicate unittest case inventory")
        if os.environ.get("MLF_TEST_LIST") == "1":
            import json
            print(json.dumps(ids))
            raise SystemExit(0)
        events.plan(ids)
        return super().run(suite)


def main(args):
    unittest.TextTestRunner = EvidenceRunner
    unittest.runner.TextTestRunner = EvidenceRunner
    if args[:2] == ["-m", "unittest"]:
        sys.argv = ["unittest", *args[2:]]
        sys.path.insert(0, os.getcwd())
        runpy.run_module("unittest", run_name="__main__")
    else:
        script = Path(args[0]).resolve()
        sys.argv = [str(script), *args[1:]]
        sys.path.insert(0, str(script.parent))
        runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main(sys.argv[1:])
