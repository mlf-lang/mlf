"""Explicit ABI adaptation of retained finite controls; original files stay frozen."""
from pathlib import Path
import difflib
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|--[^\n]*|[A-Za-z_][A-Za-z0-9_\']*|.', re.S)

def numeric_types(text):
    # Only host-side type names/conversions change. String fixtures are opaque.
    result = ''.join('Int64' if t == 'Integer' else 'fromIntegral' if t in ('toInteger','fromInteger') else t
                     for t in TOKEN.findall(text))
    if result != text:
        result = re.sub(r'^import ', 'import Data.Int (Int64)\nimport ', result, count=1, flags=re.M)
    return result

def prepare(root, out, suite):
    root, out = Path(root), Path(out)
    out.mkdir(exist_ok=False, parents=True)
    raw_manifest = (HERE/'legacy-controls-pins.json').read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != '254c26c2165f155b027a495bc7ec1c4c25d6cede6d5e1dc302621f597b3b45b3':
        raise ValueError('fixed legacy control identity manifest')
    manifest = json.loads(raw_manifest)
    supplemental = {
        'tools/performance/crate-optimizations/p2/NativeCompatibilityControls.hs':
            '54ec6908d8ef2e94e3853dc6f7f46c37b9028e9c7e4678ddf4d859b0265f264a',
    }
    ledger = []
    def copy(relative, name=None, transform=lambda s:s):
        path = root/relative
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest['files'].get(relative, supplemental.get(relative)):
            raise ValueError('frozen legacy control changed: '+relative)
        before = raw.decode('utf-8'); after = transform(before)
        dest = out/(name or path.name); dest.write_bytes(after.encode('utf-8'))
        delta = list(difflib.ndiff(before.splitlines(keepends=True), after.splitlines(keepends=True)))
        if ''.join(difflib.restore(delta, 1)) != before or ''.join(difflib.restore(delta, 2)) != after:
            raise ValueError('control adaptation inverse')
        (out/(dest.name+'.ndiff')).write_text(''.join(delta))
        ledger.append({'source':str(path),'source_sha256':hashlib.sha256(raw).hexdigest(),
                       'copy':str(dest),'copy_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
                       'inverse_verified':True,'unchanged':before==after})
        return dest
    def main_as(name):
        def change(s):
            if s.count('module Main where') != 1: raise ValueError('one control entry header')
            return numeric_types(s).replace('module Main where','module '+name+' where')
        return change
    base='tools/performance/crate-optimizations/'
    modules=[]
    if suite=='p123':
        for name in ['FrozenSelectorMap.hs','FrozenSelectorSet.hs']:
            copy(base+'p1/'+name)
        copy(base+'p1/FrozenSelectors.hs', transform=lambda s:s.replace(
             'import qualified Bootstrap.Map as M;', 'import qualified FrozenSelectorMap as M;').replace(
             'import qualified Bootstrap.Set as Set;', 'import qualified FrozenSelectorSet as Set;'))
        copy(base+'p1/SelectorDifferential.hs','P1Controls.hs',main_as('P1Controls'))
        copy(base+'p2/FrozenFingerprint.hs',transform=lambda s:'{-# OPTIONS_GHC -fno-enable-rewrite-rules -fomit-interface-pragmas -dcore-lint #-}\n'+s)
        copy(base+'p2/FingerprintDifferential.hs','P2Controls.hs',main_as('P2Controls'))
        copy(base+'p2/NativeCompatibilityControls.hs')
        for name in ['FrozenPrefix.hs','FrozenInferenceUnit.hs','QueryV6Bridge.hs']:
            copy(base+'p3/'+name)
        def prefix(s):
            s=main_as('P3Controls')(s)
            seeds='[(-1,-1),(-123456789012345678901234567890,3),(0,1),(9,-23),(2147483650,2147483640)]'
            if s.count(seeds)!=1:raise ValueError('retained five signed seed controls')
            s=s.replace(seeds,'('+seeds+' ++ [(minBound,maxBound),(maxBound,minBound),(maxBound,maxBound),(0,maxBound),(maxBound,0),(2^62,1),(1,2^62)])')
            old='import qualified Bootstrap.CrateQuery as Q\n'
            if s.count(old)!=1 or s.count('main = do\n')!=1:raise ValueError('frozen P3 bridge insertion')
            return s.replace(old,'import qualified QueryV6Bridge as Q\n').replace('main = do\n','main = do\n  Q.validateBridge\n')
        copy(base+'p3/PrefixControls.hs','P3Controls.hs',prefix)
        modules=['P1Controls','P2Controls','NativeCompatibilityControls','P3Controls']
    elif suite=='map-balance':
        copy('tools/performance/a1-private-index/controls/FrozenMap.hs')
        copy('tools/performance/map-balance/BaselineMap.hs')
        copy('tools/performance/map-balance/BalanceControls.hs','BalanceControls.hs',main_as('BalanceControls'))
        modules=['BalanceControls']
    elif suite=='fingerprint':
        folder='tools/performance/fingerprint-fusion/controls/'
        copy(folder+'Oracle.hs',transform=numeric_types)
        copy(folder+'Probe.hs')
        def fingerprint(s):
            s=numeric_types(s).replace('module Tests (main) where','module FingerprintTests (main) where')
            # 2^1024 wraps to zero under Int64. Keep this particular demand
            # probe on the noncanonical branch instead of silently losing it.
            s=s.replace('actual (2^1024) (diverge (i*10+3))','actual (-1) (diverge (i*10+3))')
            s=s.replace('  finiteValues\n','  finiteValues\n  checkPairs "additional signed Int64 interiors" [(s,c) | s <- [minBound,minBound+1,-(2^62),2^62,maxBound-1,maxBound], c <- [-1,0,1,minBound,maxBound]]\n')
            return s
        copy(folder+'Tests.hs','FingerprintTests.hs',fingerprint)
        modules=['FingerprintTests']
    else:raise ValueError('unknown legacy control family')
    (out/'adaptations.json').write_text(json.dumps({'suite':suite,'cases_removed':0,
        'scope':'Int64 ABI qualification; not an unchanged arbitrary-Integer contract',
        'frozen_files_preserved':True,'changes':ledger},indent=2)+'\n')
    return modules, ledger
