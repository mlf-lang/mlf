#!/usr/bin/env python3
"""Complete retained controls plus independent private projection-view models."""
from pathlib import Path
import hashlib,importlib.util
HERE=Path(__file__).resolve().parent
RETAINED=HERE.parent/'c3-delayed-index'
PINS={'c3-delayed-index/Main.hs': '32b887ede21a124ae7f9c8c5e544e65aa9d548998e3a213176c8cfdb47ddf102', 'c3-survivors/Main.hs': 'cd829eb6a8c7d1ef012bbda03edbaaffe07c2b596454fae4bf759fd7aa7a404b'}


def main():
    for relative,digest in PINS.items():
        if hashlib.sha256((HERE.parent/relative).read_bytes()).hexdigest()!=digest:
            raise ValueError('complete retained control changed '+relative)
    spec=importlib.util.spec_from_file_location('retained_transport',RETAINED/'run_controls.py')
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    driver.BASELINE='5172c4ade3b3141da2e64593c383892575b36699'
    driver.BASELINE_SHA='51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9'
    driver.HERE=HERE
    driver.CASE_PREFIX='private-projection-views/'
    driver.EXPECTED+=('PASS 29160 independent sparse/wide signed fresh-delta models\n'
        'PASS exact unchanged/changed Node reuse and opaque delta payloads\n'
        'PASS 720 independent projection views and cached cardinalities\n'
        'PASS 9 projection view payload-demand and first-error observations\n').encode()
    driver.EXTRA_SOURCES=[(RETAINED/'Main.hs','RetainedC3.hs',b'module Main where',b'module RetainedC3 where'),
        (HERE.parent/'c3-survivors/Main.hs','RetainedSurvivors.hs',b'module Main where',b'module RetainedSurvivors where')]
    driver.EXTRA_PINS=[Path(__file__)]
    driver.main()


if __name__=='__main__':main()
