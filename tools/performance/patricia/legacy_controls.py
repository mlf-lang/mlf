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

def prior_writer_declarations(prior):
    if hashlib.sha256(prior).hexdigest() != '88758de08e6ac15b37381b8e78dd5e47d2b50e535794aa3056513fda969fab0a':
        raise ValueError('complete prior CrateArtifact source identity')
    start, end = b'  writeObject prefix object =', b'  showInterfaceFile path ='
    if prior.count(start) != 1 or prior.count(end) != 1:
        raise ValueError('exact prior writer declaration boundaries')
    writers = prior[prior.index(start):prior.index(end)]
    if hashlib.sha256(writers).hexdigest() != '8a6c58e021d4e687617af3ab309d7aeb0dc3ee9a41c0d7b0aee6ee66b0f4ed40':
        raise ValueError('complete authenticated prior writer declarations')
    return writers

def prepare_binary_p2(root, out, copy, main_as, ledger):
    """Explicitly separate retained legacy writer proof from current binary IO."""
    import importlib.util
    adapter_path = root/'tools/performance/artifact-binary/source_migration_adapter.py'
    spec = importlib.util.spec_from_file_location('p2_binary_source_contract', adapter_path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    contract = adapter.live_contract(root/'tools/performance', source_root=root.resolve())
    owner = root/'libraries/mlf-crates/Bootstrap/CrateArtifact.hs'
    prior = contract.restore_path(owner.read_bytes(), str(owner.relative_to(root)))
    writers = prior_writer_declarations(prior)
    # The new envelope constructor is outside this historical two-variant proof.
    # Add an explicit refusal, never relax exhaustiveness or silently serialize it.
    declarations = writers.decode().replace(
        'LegacyCrateObject _ _ -> encodeObjectWithInterface object interfaceText',
        'LegacyCrateObject _ _ -> encodeObjectWithInterface object interfaceText;\n'
        '        EnvelopeCrateObject _ _ _ -> Host.errorWithoutStackTrace "legacy writer projection excludes envelope objects"')
    declarations = declarations.replace('encodeObjectWithInterface object interfaceText',
        'encodeObjectWithInterface (legacyOnly object) interfaceText')
    projected = ('{-# LANGUAGE NoImplicitPrelude, OverloadedStrings #-}\n'
        'module LegacyArtifactWriter (module A, writeObject, writeObjectWithPayload) where {\n'
        '  import MLF.Primitive;\n'
        '  import qualified Prelude as Host;\n'
        '  import Bootstrap.CrateArtifact as A hiding (writeObject, writeObjectWithPayload);\n'
        '  legacyOnly object = case object of {\n'
        '    CrateObject _ _ -> object; LegacyCrateObject _ _ -> object;\n'
        '    EnvelopeCrateObject _ _ _ -> Host.errorWithoutStackTrace "legacy writer projection excludes envelope objects"\n'
        '  };\n' + declarations + '}\n')
    def retain(relative, name, data):
        source = root/relative
        before = source.read_text()
        path = out/name
        path.write_text(data)
        delta = list(difflib.ndiff(before.splitlines(keepends=True), data.splitlines(keepends=True)))
        if ''.join(difflib.restore(delta, 1)) != before or ''.join(difflib.restore(delta, 2)) != data:
            raise ValueError('binary writer adaptation inverse')
        (out/(name+'.ndiff')).write_text(''.join(delta))
        ledger.append({'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'copy':str(path),'copy_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'inverse_verified':True,'unchanged':before==data,
            'scope':'explicit projected legacy writer or active binary writer control; not a frozen public-IO equivalence claim'})
    retain(str(owner.relative_to(root)), 'LegacyArtifactWriter.hs', projected)
    def retained(s):
        s = main_as('RetainedP2Controls')(s)
        needle = 'import qualified Bootstrap.CrateArtifact as A\n'
        if s.count(needle) != 1: raise ValueError('one explicit P2 artifact import')
        return s.replace(needle, 'import qualified LegacyArtifactWriter as A\n')
    copy('tools/performance/crate-optimizations/p2/FingerprintDifferential.hs',
         'RetainedP2Controls.hs', retained)
    current = 'tools/performance/artifact-binary/BinaryP2WriterControls.hs'
    retain(current, 'BinaryP2WriterControls.hs', (root/current).read_text())
    wrapper = ('module P2Controls where\n'
        'import qualified RetainedP2Controls as Legacy\n'
        'import qualified BinaryP2WriterControls as Binary\n'
        'main = do\n'
        '  putStrLn "P2 retained 2503: current pure/fingerprint encoders and authenticated prior text-writer projection; not current binary IO"\n'
        '  Legacy.main\n'
        '  Binary.main\n')
    retain('tools/performance/patricia/legacy_controls.py','P2Controls.hs',wrapper)
    (out/'binary-writer-projection.json').write_text(json.dumps({
        'format':'explicit-p2-binary-writer-transition-v1',
        'prior_owner_sha256':hashlib.sha256(prior).hexdigest(),
        'prior_writer_declarations_sha256':hashlib.sha256(writers).hexdigest(),
        'binary_source_contract_sha256':contract.manifest_sha256,
        'retained_control_count':2503,'retained_scope':'pure/fingerprint and projected prior text writers',
        'actual_binary_control_count':184,'actual_binary_required_before_return':True,
        'envelope_constructor':'explicitly refused by legacy projection',
        'independent_wire_scope':'fixed header, sections, widths and CRC; not a full independent typed decoder',
        'frozen_originals_unchanged':True},indent=2)+'\n')

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
        prepare_binary_p2(root, out, copy, main_as, ledger)
        copy(base+'p2/NativeCompatibilityControls.hs')
        for name in ['FrozenPrefix.hs','FrozenInferenceUnit.hs']:
            copy(base+'p3/'+name)
        # This historical bridge projects only an empty group and an opaque
        # caller-supplied context. Keep its controls and inverse transcript.
        copy(base+'p3/QueryV6Bridge.hs', transform=lambda s:
             s.replace('MLF-SOURCE-CRATE-QUERY-6','MLF-SOURCE-CRATE-QUERY-7'))
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
        'scope':('Int64 ABI qualification; retained P2 pure/fingerprint and projected prior text writer controls; separate required actual public binary writer controls; not unchanged public writer IO or full linker admission' if suite=='p123' else 'Int64 ABI qualification; not an unchanged arbitrary-Integer contract'),
        'frozen_files_preserved':True,'changes':ledger},indent=2)+'\n')
    return modules, ledger
