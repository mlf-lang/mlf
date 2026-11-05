#!/usr/bin/env python3
"""Complete retained controls plus independent private projection-view models."""
from pathlib import Path
import hashlib,importlib.util
HERE=Path(__file__).resolve().parent
RETAINED=HERE.parent/'c3-delayed-index'
PINS={'c3-delayed-index/Main.hs': '61545209bd6709a4cdd26fc0dd794b709bd74438b503520ed957f3f84db6b02e', 'c3-survivors/Main.hs': '711c186635228363792068cc80fae0ee0afffe0313f274caeab4d93a644efa09'}


def main():
    for relative,digest in PINS.items():
        if hashlib.sha256((HERE.parent/relative).read_bytes()).hexdigest()!=digest:
            raise ValueError('complete retained control changed '+relative)
    spec=importlib.util.spec_from_file_location('retained_transport',RETAINED/'run_controls.py')
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    driver.BASELINE='5172c4ade3b3141da2e64593c383892575b36699'
    driver.BASELINE_SHA='51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9'
    driver.HERE=HERE
    driver.EXPECTED+=('PASS 29160 independent sparse/wide signed fresh-delta models\n'
        'PASS exact unchanged/changed Node reuse and opaque delta payloads\n'
        'PASS 720 independent projection views and cached cardinalities\n'
        'PASS 9 projection view payload-demand and first-error observations\n').encode()
    driver.EXTRA_SOURCES=[(RETAINED/'Main.hs','RetainedC3.hs',b'module Main where',b'module RetainedC3 where'),
        (HERE.parent/'c3-survivors/Main.hs','RetainedSurvivors.hs',b'module Main where',b'module RetainedSurvivors where')]
    driver.EXTRA_PINS=[Path(__file__)]
    driver.main()


if __name__=='__main__':main()
