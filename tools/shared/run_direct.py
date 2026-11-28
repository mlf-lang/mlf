#!/usr/bin/env python3
"""Run authenticated direct suites with bounded descendant cleanup."""
import os
import test_direct
from direct_managed import ManagedRunner


def main():
    if os.environ.get('MLF_TEST_EXACT'):
        import direct_candidate_focus
        direct_candidate_focus.run(test_direct, direct_candidate_focus.selected_label(),
                                   runner_factory=ManagedRunner)
    else:
        test_direct.main(runner_factory=ManagedRunner)


if __name__ == '__main__':
    main()
