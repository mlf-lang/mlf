#!/usr/bin/env python3
"""Complete retained controls plus independent private projection-view models."""
from pathlib import Path
import importlib.util
HERE=Path(__file__).resolve().parent
RETAINED=HERE.parent/'c3-delayed-index'


def main():
    # Retained controls are maintained test sources; the transport hashes all inputs.
    spec=importlib.util.spec_from_file_location('retained_transport',RETAINED/'run_controls.py')
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    driver.BASELINE='5172c4ade3b3141da2e64593c383892575b36699'
    # Separate baseline oracle, with only its module/export header rewritten.
    driver.ORACLE_SHA='3d894631f51bb52670eaff12afba6ffaf0a076c5283617ee6f29b4755fc9c67d'
    driver.HERE=HERE
    driver.CASE_PREFIX='private-projection-views/'
    driver.EXPECTED+=('PASS 29160 independent sparse/wide signed fresh-delta models\n'
        'PASS exact unchanged/changed Node reuse and opaque delta payloads\n'
        'PASS 720 independent projection views and cached cardinalities\n'
        'PASS 9 projection view payload-demand and first-error observations\n').encode()
    driver.EXTRA_SOURCES=[(RETAINED/'Main.hs','RetainedC3'),
        (HERE.parent/'c3-survivors/Main.hs','RetainedSurvivors')]
    driver.EXTRA_PINS=[Path(__file__)]
    driver.main()


if __name__=='__main__':main()
