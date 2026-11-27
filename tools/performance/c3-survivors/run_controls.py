#!/usr/bin/env python3
"""Retain full C3 owner controls and add independent fresh-delta model checks."""
from pathlib import Path
import importlib.util

HERE=Path(__file__).resolve().parent
RETAINED=HERE.parent/'c3-delayed-index'
# Compile the complete maintained control. The transport records its input hash.


def main():
    original=RETAINED/'Main.hs'
    spec=importlib.util.spec_from_file_location('c3_control_transport',RETAINED/'run_controls.py')
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    driver.HERE=HERE
    driver.CASE_PREFIX='fresh-survivors/'
    driver.EXPECTED+=('PASS 29160 independent sparse/wide signed fresh-delta models\n'
                      'PASS exact unchanged/changed Node reuse and opaque delta payloads\n').encode()
    driver.EXTRA_SOURCES=[(original,'RetainedC3')]
    driver.EXTRA_PINS=[Path(__file__)]
    driver.main()


if __name__=='__main__':main()
