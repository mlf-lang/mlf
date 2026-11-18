#!/usr/bin/env python3
"""Prepare an exact limited-source Map qualification, never a full producer.
Historical Map comes from physical fc300 Git bytes, not restore_path. Current
selected bytes are bound to immutable remote5d contents, not local HEAD.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import stat
import subprocess

CURRENT_COMMIT = '5d590d53d701dfb7053c813ca068ea1f0ef0ed55'
CURRENT_TREE = '7a3297c550fe33ff0e0321f188a786c7cc6e5d71'
HISTORICAL_COMMIT = 'fc300bc9fdc389b585cbef0630fc8915d53e89c5'
HISTORICAL_TREE = '386f0b41ab5f9b39fca273f3040f51d73df924a1'
MAP = 'libraries/mlf-foundation/Bootstrap/Map.hs'
BALANCE = 'tools/performance/map-balance/BalanceControls.hs'
BASELINE = 'tools/performance/map-balance/BaselineMap.hs'
FROZEN = 'tools/performance/a1-private-index/controls/FrozenMap.hs'
CURRENT_MAP_SHA = 'c2d233fcee19279dc730582683c13b40edf62d0caa2091c3d75d86953a551996'
HISTORICAL_MAP_SHA = '1ef3465e36c4fddcb2b2e60fafd27b642a79e956fe8357355b798d1c7ab199b0'
HISTORICAL_MAP_BLOB = '7a96f912d4a5bbd7e8291c0df4042bd56a9c8c65'
ORACLE_SHA = {
    BALANCE: 'badfdff0f04a5612d8ffc4ba496feb6344ab9c5da5f7a750cb82e8eca586fb80',
    FROZEN: '0cdeb2b572f38a59e82e5a91d3c47b118b5dc0928292a66849115e1679d18e31',
    BASELINE: 'fca037e0cd1719142ff7bc825aa811359d9f84b9030d774713ffa5046d1bf7e7',
}
# GitHub Contents API, each path fetched at CURRENT_COMMIT.
CURRENT_BLOBS = {
    "runtime/mlf_process_supervisor_posix.h": "4ab02a329811f04172ffed9413cb2f8165bce060",
    "runtime/mlf_windows_path.h": "d93a6d2c98da5d0e976b2eb746cb0e2fc1c9412d",
    "runtime/mlf_system_windows.h": "da1d174365ef245ad701949058f1c060552eb1b1",
    "libraries/mlf-foundation/Bootstrap/Map.hs": "39bf6af3d4175fa187d81a0112dcb2f755444521",
    "libraries/mlf-foundation/Bootstrap/Types.hs": "ed4a3788f5c8a500e497e3a136a430983b157eb7",
    "libraries/mlf-foundation/Bootstrap/Std.hs": "8e7a513d336815f313ab63be975ce4af3303554c",
    "libraries/mlf-foundation/Bootstrap/IndexVec.hs": "33a339e71ad7dede8c866a1903bf85bad1034d13",
    "host/ghc/MLF/Primitive.hs": "2ede543a36ffd6e5bffb51702853b4e16209cda9",
    "host/ghc/MLF/Host/Base.hs": "9b1eeed9e1299492bb83c7255014e6b2da8d5bb2",
    "host/ghc/MLF/Host/IO.hs": "5cefc2fdd2ea036cddc75803254ed5956b4401a0",
    "host/ghc/MLF/Host/Async.hs": "601bb2e08f7be500646d9cae520b068c83640686",
    "host/ghc/cbits/host.c": "0c5880eadb1c94d8fe2431e645f0317e52a401f7",
    "runtime/mlf_process_supervisor.c": "7efde0ab6d2d5542f30c44422bf90f95885918e3",
    "runtime/mlf_build_runner_hash.h": "d40e996576990551ca32e6f1cea75a4bde49828a",
    "runtime/mlf_byte_file.h": "b07a62af37d6dff4211070897246e29ec9e8f0a2",
    "runtime/mlf_process_binding.h": "0c685af2677aa71a47471eb3978bb94742b523c6",
    "runtime/mlf_process_supervisor.h": "dd5b4300c178423497727e0de9f6bc56beeadf59",
    "runtime/mlf_system.h": "b7212f33d646729bcd10842ade489f54da125349",
    "runtime/mlf_windows.h": "3b35be83f13ee4d31a879a801e94250538e2a61a",
    "tools/performance/map-balance/BalanceControls.hs": "f5f96a00e424f89f6b082c943d139d17d4ce367d",
    "tools/performance/map-balance/BaselineMap.hs": "9767ba8ffc25380fd86b1bb5862a189d7d2f2c40",
    "tools/performance/a1-private-index/controls/FrozenMap.hs": "f2ffc43de3672417b08ea749dd58786978e751fc"
}
MAX_BYTES = 1024 * 1024
NUMERIC_LINES = tuple(line.encode() for line in [
    "data Shape = Empty | Node Integer Integer Integer Shape Shape deriving (Eq,Show)",
    "shape :: T.Map Integer Integer -> Shape",
    "cmp :: Integer -> Integer -> Integer",
    "leaf :: Integer -> T.Map Integer Integer",
    "mk :: Integer -> Int -> Integer -> T.Map Integer Integer",
    "      let k=toInteger ((i*37) `mod` 97-48); v=toInteger i",
    "type Tree=T.Map Integer Integer",
    "type Balance=Integer -> Integer -> Tree -> Tree -> Tree",
    "node :: Integer -> Integer -> Tree -> Tree -> Tree"
])
EXPECTED_STDOUT = b'Balance controls: 24649 raw-shape pairs; 400 mutation steps; 30 independent demand/order cases passed\n'

def require(value, message):
    if not value:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()

def read_regular(root, relative):
    path = Path(root)
    for part in Path(relative).parts:
        require(part not in ('..', '.', '/') and part, 'relative source path')
        path = path / part
        require(not path.is_symlink(), 'symlink source forbidden: ' + relative)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES, 'bounded regular source: ' + relative)
    raw = path.read_bytes()
    require(len(raw) <= MAX_BYTES, 'source changed size: ' + relative)
    return raw

def validate_context(current_commit, current_tree, historical_commit, historical_tree):
    require((current_commit, current_tree) == (CURRENT_COMMIT, CURRENT_TREE), 'exact remote current source context')
    require((historical_commit, historical_tree) == (HISTORICAL_COMMIT, HISTORICAL_TREE), 'exact physical historical source context')

def authenticate_inputs(current, historical_map, context):
    validate_context(*context)
    require(type(current) is dict and set(current) == set(CURRENT_BLOBS), 'exact limited input inventory')
    for path, raw in current.items():
        require(type(raw) is bytes and len(raw) <= MAX_BYTES and blob(raw) == CURRENT_BLOBS[path], 'remote current blob: ' + path)
    for path, expected in ORACLE_SHA.items():
        require(sha(current[path]) == expected, 'entire retained oracle: ' + path)
    require(sha(current[MAP]) == CURRENT_MAP_SHA, 'current Map endpoint')
    require(type(historical_map) is bytes and len(historical_map) <= MAX_BYTES and
            sha(historical_map) == HISTORICAL_MAP_SHA and blob(historical_map) == HISTORICAL_MAP_BLOB,
            'physical fc300 Map endpoint')
    project_include_graph(current)

def project_include_graph(current):
    pending = ['host/ghc/cbits/host.c', 'runtime/mlf_process_supervisor.c']
    graph = {}
    while pending:
        path = pending.pop()
        if path in graph:
            continue
        edges = []
        for name in re.findall(rb'^\s*#\s*include\s*"([^"]+)"', current[path], re.M):
            require(b'/' not in name and b'\\' not in name, 'fixed bare project include')
            target = 'runtime/' + name.decode('ascii')
            require(target in current, 'unbound transitive project include: ' + target)
            edges.append(target)
            pending.append(target)
        graph[path] = edges
    require(set(graph) == {p for p in current if p.endswith(('.c', '.h'))},
            'exact conservative project C/header closure')
    return graph

def changes(module, historical=False):
    require(module in ('RetainedBalanceControls', 'HistoricalBalanceControls'), 'fixed control module')
    require(historical == (module == 'HistoricalBalanceControls'), 'fixed module and candidate pairing')
    result = [(b'module Main where\n', ('module ' + module + ' where\n').encode()),
              (b'import Prelude\n', b'import Data.Int (Int64)\nimport Prelude\n')]
    for old in NUMERIC_LINES:
        new = old.replace(b'toInteger', b'fromIntegral').replace(b'Integer', b'Int64')
        result.append((old + b'\n', new + b'\n'))
    if historical:
        result.append((b'import qualified Bootstrap.Map as C\n', b'import qualified HistoricalMap as C\n'))
    return result

def apply_unique(raw, edits):
    changed = raw
    for old, new in edits:
        require(old != new and changed.count(old) == 1 and new not in changed, 'unique declared adaptation')
        changed = changed.replace(old, new)
    require(invert_unique(changed, edits) == raw, 'complete adaptation inverse')
    return changed

def invert_unique(changed, edits):
    raw = changed
    for old, new in reversed(edits):
        # An inserted import intentionally contains the original import. Only
        # replacement uniqueness is required; full restored bytes are pinned.
        require(raw.count(new) == 1, 'unique inverse adaptation')
        raw = raw.replace(new, old)
    return raw

def prepare_bytes(current, historical_map, context):
    authenticate_inputs(current, historical_map, context)
    retained = current[BALANCE]
    return {
        'RetainedBalanceControls.hs': apply_unique(retained, changes('RetainedBalanceControls')),
        'HistoricalBalanceControls.hs': apply_unique(retained, changes('HistoricalBalanceControls', True)),
        'HistoricalMap.hs': apply_unique(historical_map, [(b'module Bootstrap.Map where {', b'module HistoricalMap where {')]),
        'FrozenMap.hs': current[FROZEN],
        'BaselineMap.hs': current[BASELINE],
    }

def verify_generated(generated, current, historical_map, context):
    require(type(generated) is dict and generated == prepare_bytes(current, historical_map, context),
            'exact generated inventory and bytes; no extra adaptation')
    for name, historical in [('RetainedBalanceControls', False), ('HistoricalBalanceControls', True)]:
        restored = invert_unique(generated[name + '.hs'], changes(name, historical))
        require(restored == current[BALANCE] and sha(restored) == ORACLE_SHA[BALANCE], 'complete original control restored')
    restored = invert_unique(generated['HistoricalMap.hs'], [(b'module Bootstrap.Map where {', b'module HistoricalMap where {')])
    require(restored == historical_map and sha(restored) == HISTORICAL_MAP_SHA, 'physical historical Map restored')

def historical_from_git(repository, output=subprocess.check_output):
    prefix = ['git', '--no-replace-objects', '-C', str(repository)]
    actual_tree = output([*prefix, 'rev-parse', HISTORICAL_COMMIT + '^{tree}'], timeout=30).decode().strip()
    require(actual_tree == HISTORICAL_TREE, 'fixed historical Git tree')
    raw = output([*prefix, 'show', HISTORICAL_COMMIT + ':' + MAP], timeout=30)
    require(len(raw) <= MAX_BYTES and sha(raw) == HISTORICAL_MAP_SHA and blob(raw) == HISTORICAL_MAP_BLOB,
            'actual historical Git Map blob')
    return raw

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--current-commit', required=True)
    p.add_argument('--current-tree', required=True)
    a = p.parse_args()
    context = (a.current_commit, a.current_tree, HISTORICAL_COMMIT, HISTORICAL_TREE)
    validate_context(*context)
    current = {path: read_regular(a.source, path) for path in CURRENT_BLOBS}
    historical = historical_from_git(a.source)
    generated = prepare_bytes(current, historical, context)
    verify_generated(generated, current, historical, context)
    out = a.output.resolve()
    source = a.source.resolve()
    require(not out.exists() and out != source and not source.is_relative_to(out) and not out.is_relative_to(source),
            'fresh output separate from source tree and ancestors')
    out.mkdir(parents=True, exist_ok=False)
    for name, raw in generated.items():
        (out / name).write_bytes(raw)
        require((out / name).read_bytes() == raw, 'generated write verification')
    for path, raw in current.items():
        target = out / 'source' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        require(target.read_bytes() == raw, 'source snapshot write verification')
    original = out / 'originals'
    original.mkdir()
    for path in ORACLE_SHA:
        (original / Path(path).name).write_bytes(current[path])
        require((original / Path(path).name).read_bytes() == current[path], 'original write verification')
    (original / 'fc300-Map.hs').write_bytes(historical)
    require((original / 'fc300-Map.hs').read_bytes() == historical, 'historical write verification')
    ledger = {
        'prepared': True, 'qualification_complete': False, 'performance_measured': False,
        'scope': '8-module current source closure plus 2 FFI C sources and 9 project headers; not full producer authentication',
        'current_commit': CURRENT_COMMIT, 'current_tree': CURRENT_TREE,
        'historical_commit': HISTORICAL_COMMIT, 'historical_tree': HISTORICAL_TREE,
        'current_inputs': {path: {'git_blob': CURRENT_BLOBS[path], 'sha256': sha(raw)} for path, raw in current.items()},
        'historical_map': {'path': MAP, 'git_blob': HISTORICAL_MAP_BLOB, 'sha256': sha(historical)},
        'generated_sha256': {name: sha(raw) for name, raw in generated.items()},
        'original_oracle_sha256': ORACLE_SHA, 'historical_expected_stdout': EXPECTED_STDOUT.decode(),
        'adaptation': 'exact unique numeric lines, Data.Int import, module headers and historical candidate import; entire-byte inverse verified',
        'shared_base': 'Both Map policies share exact current Types/Std/IndexVec and four host modules; not a full historical runtime.',
        'ffi': {'sources': ['host/ghc/cbits/host.c', 'runtime/mlf_process_supervisor.c'], 'include': '-Iruntime'},
        'project_include_graph': project_include_graph(current),
        'platform_scope': 'Planned Linux execution. Conservative project-header closure also retains conditional Windows inputs; conditions remain exact pinned source, not rewritten.',
        'external_include_requirements': ['GHC MachDeps.h from Host/IO.hs CPP; authenticate with actual toolchain', 'system angle-bracket C headers and linked libraries require execution-time toolchain evidence'],
        'toolchain_and_system_dependencies_authenticated': False,
        'adapter_sha256': sha(Path(__file__).read_bytes()),
    }
    (out / 'preparation.json').write_text(json.dumps(ledger, indent=2) + '\n')

if __name__ == '__main__':
    main()
