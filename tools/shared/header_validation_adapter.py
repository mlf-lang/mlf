"""Strict, reversible two-lane HeaderValidationTests adaptation.
Historical lane qualifies only four historical formatter bodies against current
shared foundational modules, never a complete historical compiler.
"""
from pathlib import Path
import hashlib
import json
import subprocess

FIXTURE_BLOB = 'aa411949945d62c17a21c1191abd93fa7c5fd8ea'
HISTORICAL_BLOB = 'dd5b4630a80803c19afdb219dba2dc4bffc3ea1b'
START = b'  definitionName ::'
END = b'  startsWith'
HEADER = b'''{-# LANGUAGE NoImplicitPrelude, OverloadedStrings #-}
module HistoricalHeaderNames where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Separate as Separate;
'''
FOOTER = b'}\n'
IMPORT = b'import qualified Bootstrap.CrateArtifact as A\n'
HISTORY_EDITS = [
    (IMPORT, IMPORT + b'import qualified HistoricalHeaderNames as H\nimport qualified HeaderNamingOracle as N\n'),
    (b'A.definitionName identity e', b'H.definitionName identity e'),
    (b'A.definitionNameEncoded (S.encoded identity) e',
     b'H.definitionNameEncoded (S.encoded identity) e'),
    (b' putStrLn "PASS header duplicate errors, entity identity, Unicode naming and forged primitive rejection"',
     b' N.historicalControls\n putStrLn "PASS header duplicate errors, entity identity, Unicode naming and forged primitive rejection"'),
]
CURRENT_EDITS = [
    (IMPORT, IMPORT + b'import qualified HeaderNamingOracle as N\n'),
    (b'let expected=oldName identity e', b'let expected=N.currentName identity e'),
    (b'A.definitionNameEncoded (S.encoded identity) e',
     b'A.definitionNameEncoded (N.encoded identity) e'),
    (b' putStrLn "PASS header duplicate errors, entity identity, Unicode naming and forged primitive rejection"',
     b' N.controls\n putStrLn "PASS header duplicate errors, entity identity, Unicode naming and forged primitive rejection"'),
]

def require(ok, message):
    if not ok:
        raise ValueError(message)

def blob_id(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def authenticate(data, expected):
    require(isinstance(data, bytes) and blob_id(data) == expected, 'source blob identity')
    return data

def replace_once(data, old, new):
    require(data.count(old) == 1, 'unique adaptation boundary')
    return data.replace(old, new, 1)

def transform(data, edits):
    for old, new in edits:
        data = replace_once(data, old, new)
    return data

def adapt_fixture(raw, lane):
    authenticate(raw, FIXTURE_BLOB)
    require(lane in ('historical', 'current'), 'unknown lane')
    edits = HISTORY_EDITS if lane == 'historical' else CURRENT_EDITS
    result = transform(raw, edits)
    require(transform(result, [(b,a) for a,b in reversed(edits)]) == raw,
            'fixture inverse')
    return result

def restore_fixture(generated, lane):
    require(lane in ('historical', 'current'), 'unknown lane')
    edits = HISTORY_EDITS if lane == 'historical' else CURRENT_EDITS
    raw = transform(generated, [(b,a) for a,b in reversed(edits)])
    authenticate(raw, FIXTURE_BLOB)
    require(adapt_fixture(raw, lane) == generated, 'fixture regeneration')
    return raw

def historical_module(raw):
    authenticate(raw, HISTORICAL_BLOB)
    require(raw.count(START) == 1 and raw.count(END) == 1, 'historical boundaries')
    begin, end = raw.index(START), raw.index(END)
    require(begin < end, 'historical range')
    body = raw[begin:end]
    require(body.count(b' :: ') == 4, 'four complete formatter functions')
    generated = HEADER + body + FOOTER
    require(generated[len(HEADER):-len(FOOTER)] == body, 'historical inverse')
    require(raw[:begin] + generated[len(HEADER):-len(FOOTER)] + raw[end:] == raw,
            'historical full-source inverse')
    return generated, body

def fixed_history(root):
    result = subprocess.run(['git', '--no-replace-objects', 'cat-file', 'blob', HISTORICAL_BLOB],
                            cwd=root, capture_output=True, check=True, timeout=30)
    require(not result.stderr, 'historical Git diagnostic')
    return authenticate(result.stdout, HISTORICAL_BLOB)

def prepare(root, output, raw_history=None):
    root, output = Path(root), Path(output)
    fixture = root / 'tools/shared/fixtures/native/HeaderValidationTests.hs'
    oracle = root / 'tools/shared/fixtures/native/HeaderNamingOracle.hs'
    raw = fixture.read_bytes()
    old = fixed_history(root) if raw_history is None else raw_history
    generated, body = historical_module(old)
    destination = output / 'header-validation'
    destination.mkdir(exist_ok=False)
    files = {
        'HistoricalHeaderNames.hs': generated,
        'HeaderNamingOracle.hs': oracle.read_bytes(),
        'HeaderValidationHistorical.hs': adapt_fixture(raw, 'historical'),
        'HeaderValidationCurrent.hs': adapt_fixture(raw, 'current'),
    }
    files['historical-formatter.raw'] = body
    files['HeaderValidationTests.original.hs'] = raw
    observed = {}
    for name, value in files.items():
        path = destination / name
        path.write_bytes(value)
        observed[name] = path.read_bytes()
        require(observed[name] == value, 'written artifact readback: ' + name)
    for lane, name in [('historical','HeaderValidationHistorical.hs'), ('current','HeaderValidationCurrent.hs')]:
        require(restore_fixture(observed[name], lane) == raw, 'written fixture inverse')
    require(observed['HistoricalHeaderNames.hs'][len(HEADER):-len(FOOTER)] ==
            observed['historical-formatter.raw'], 'written historical body inverse')
    evidence = {
        'format': 1, 'fixture_git_blob': FIXTURE_BLOB,
        'historical_source_git_blob': HISTORICAL_BLOB,
        'historical_scope': 'four original formatter bodies; current shared foundational modules',
        'historical_complete_compiler_qualified': False,
        'historical_body_sha256': hashlib.sha256(body).hexdigest(),
        'generated': {name: hashlib.sha256(value).hexdigest() for name,value in files.items()},
        'fixture_inverse_verified': True, 'historical_inverse_verified': True,
        'qualification_executed': False,
    }
    evidence_bytes = (json.dumps(evidence, indent=2)+'\n').encode()
    evidence_path = destination / 'adaptation.json'
    evidence_path.write_bytes(evidence_bytes)
    require(evidence_path.read_bytes() == evidence_bytes, 'adaptation evidence readback')
    return destination, evidence
