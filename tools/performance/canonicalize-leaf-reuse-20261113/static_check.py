#!/usr/bin/env python3
"""Read-only source checks; never invokes a compiler or runs Haskell."""
from pathlib import Path
import difflib
import hashlib
import json
import re
import sys

root = Path(__file__).resolve().parent
baseline = Path(sys.argv[1]) if len(sys.argv) == 2 else root.parent / 'source'
pins = json.loads((root / 'source-pins.json').read_text())
rel = Path(pins['changed_source'])
old_bytes = (baseline / rel).read_bytes()
new_bytes = (root / rel).read_bytes()
old, new = old_bytes.decode(), new_bytes.decode()
sha = lambda value: hashlib.sha256(value).hexdigest()
assert sha(old_bytes) == pins['baseline_source_sha256']
assert sha(new_bytes) == pins['candidate_source_sha256']
start = '  canonicalize :: Graph -> Graph;\n'
end = '  equationNodes :: (,) Int Int -> [] Int;\n'
def parts(text):
    prefix, middle = text.split(start)
    definition, suffix = middle.split(end)
    return prefix, start + definition, end + suffix
op, od, os = parts(old)
np, nd, ns = parts(new)
assert op == np and os == ns, 'change outside canonicalize'
expected_old = '''  canonicalize :: Graph -> Graph;
  canonicalize graph =
    mkGraph
      (mapNodes (\\node -> mkNode (mapTag (resolve graph) (tag node)) (binder node) (flag node))
         (nodes graph))
      (links graph)
      (nextId graph);
'''
assert od == expected_old
for tag in ['GBot', 'GBotK kind', 'GTyCon name kind', 'GSkolem identity kind']:
    assert nd.count(tag + ' -> node;') == 1
assert nd.count('_ -> mkNode (mapTag (resolve graph) (tag node)) (binder node) (flag node)') == 1
patch = ''.join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
    fromfile='a/' + str(rel), tofile='b/' + str(rel)))
assert (root / 'candidate.patch').read_text() == patch
assert sha(patch.encode()) == pins['patch_sha256']
# The reference expression is the exact old expression, qualified only.
reference = (root / 'CanonicalizeReference.hs').read_text().split('canonicalizeBefore graph =\n')[1]
reference = reference.replace('G.', '')
normalize = lambda text: ''.join(text.split()).removesuffix(';')
assert normalize(reference) == normalize(od.split('  canonicalize graph =\n')[1])
# Existing declarations are unchanged; the candidate adds no declarations.
declarations = lambda text: re.findall(r'^  ([a-zA-Z][a-zA-Z0-9]*) ::', text, re.M)
assert declarations(old) == declarations(new)
result = {
    'status': 'static source checks passed; no Haskell compilation/execution',
    'baseline_source_sha256': sha(old_bytes),
    'candidate_source_sha256': sha(new_bytes),
    'only_changed_definition': 'canonicalize',
    'existing_type_signatures_preserved': True,
    'reference_body_matches_frozen_expression_after_qualification': True,
    'patch_exactly_reproduces_source_difference': True,
    'compiler_tests_run': False,
    'runtime_tests_run': False,
    'performance_tests_run': False,
}
print(json.dumps(result, indent=2))
