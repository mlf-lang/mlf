#!/usr/bin/env python3
"""Retain full C3 owner controls and add independent fresh-delta model checks."""
from pathlib import Path
import hashlib
import importlib.util

HERE=Path(__file__).resolve().parent
RETAINED=HERE.parent/'c3-delayed-index'
# Keep the complete authored control, not a copied selection of its cases.
CONTROL_SHA='61545209bd6709a4cdd26fc0dd794b709bd74438b503520ed957f3f84db6b02e'


def main():
    original=RETAINED/'Main.hs'
    if hashlib.sha256(original.read_bytes()).hexdigest()!=CONTROL_SHA:
        raise ValueError('complete retained C3 control required')
    spec=importlib.util.spec_from_file_location('c3_control_transport',RETAINED/'run_controls.py')
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    driver.BASELINE='ffa3d201e4ea9c08109ff00df3f4fd66b56f3ab2'
    driver.BASELINE_SHA='157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094'
    driver.HERE=HERE
    driver.EXPECTED+=('PASS 29160 independent sparse/wide signed fresh-delta models\n'
                      'PASS exact unchanged/changed Node reuse and opaque delta payloads\n').encode()
    driver.EXTRA_SOURCES=[(original,'RetainedC3.hs',b'module Main where',b'module RetainedC3 where')]
    driver.EXTRA_PINS=[Path(__file__)]
    driver.main()


if __name__=='__main__':main()
