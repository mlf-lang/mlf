#!/usr/bin/env python3
"""Run the byte-pinned A1 assertions with the real live Phase 2 source edge."""
from pathlib import Path
import os
import sys
import unittest

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[2]
sys.path.insert(0, str(ROOT / 'tools/release'))
from check_benchmark_phase2_successor import successor

ORIGINAL = 'tools/performance/a1-private-index/test_current.py'
ORIGINAL_SHA = '49afb999c95477e458bd9c349cac3a560586cc29c93eec57e7d0d26046f9a776'
PATRICIA = 'tools/performance/patricia/source_migration.py'
PATRICIA_SHA = 'e8f77e1eed83994b3b41d2906bdc41b46274119fafa63a1336902f233c7e7830'
STOCK_FACTORY = b"""    spec = importlib.util.spec_from_file_location('actual_binary_source_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
"""
LIVE_FACTORY = b"""    return Phase2A1(phase2_contract)
"""


class Phase2A1:
    """Compose only the three actual A1 entry points. All old registry edges run."""
    def __init__(self, contract):
        self.live = contract
        self.patricia = successor.pinned_module(ROOT, PATRICIA, PATRICIA_SHA)

    def migrate(self, base):
        parent = self.patricia.migrate_to_read_window(base)
        result = self.live.advance_registry(parent)
        if self.live.live_registry(self.live.source_root) != result:
            raise ValueError('exact live Phase 2 source registry')
        return result

    def binary_contract(self):
        return self.live

    def project_binary_owner(self, raw, module):
        return self.live.project_owner(raw, module)


def load_fixture():
    old = successor.read(ROOT, ORIGINAL, 65536)
    successor.require(successor.sha(old) == ORIGINAL_SHA and old.count(STOCK_FACTORY) == 1 and
                      LIVE_FACTORY not in old, 'exact stock A1 factory')
    live = old.replace(STOCK_FACTORY, LIVE_FACTORY)
    successor.require(live.replace(LIVE_FACTORY, STOCK_FACTORY) == old,
                      'preserve every A1 test method and assertion')
    return compile(live, str(ROOT / ORIGINAL), 'exec')


if __name__ == '__main__':
    fixture = load_fixture()
    if os.environ.get('MLF_TEST_LIST') == '1':
        successor.require(unittest.TextTestRunner.__name__ == 'EvidenceRunner', 'stock discovery')
        exec(fixture, globals())
    else:
        with successor.qualified(ROOT) as opened:
            phase2_contract = opened.contract
            exec(fixture, globals())
