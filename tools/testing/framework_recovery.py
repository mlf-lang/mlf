#!/usr/bin/env python3
"""Authenticate PR19 historical repairs, independently of the evolved PR22 framework."""
import hashlib
import json
import subprocess

RECOVERED_FRAMEWORK = 'afbe7219806881301831d79f43596811eca3279d'
FROZEN_FRAMEWORK = 'e0f11f9c39b40f54f30e0eecbea7cebdf8cf0e74'
EDITS = {
    'testing/Test/Outcome.emlf': [
        ('import Bootstrap.Types\n', 'import Bootstrap.Types hiding (Phase)\n'),
    ],
    'testing/Test/Evidence.emlf': [
        ('import Bootstrap.Types\n', 'import Bootstrap.Types hiding (Binding)\n'),
        ('lookupDescriptor identity entries = case entries of\n',
         'lookupDescriptor : String -> List D.Descriptor -> Either String D.Descriptor\nlookupDescriptor identity entries = case entries of\n'),
    ],
    'testing/Test/Plan.emlf': [
        ('import Bootstrap.Types\n', 'import Bootstrap.Types hiding (Kind, Node)\n'),
        ('validateNodes seen restricted nodes = case nodes of\n',
         'validateNodes : List String -> List String -> List Node -> Either String Unit\nvalidateNodes seen restricted nodes = case nodes of\n'),
    ],
    'testing/tools/Test/Process.emlf': [
        ('  exists <- fileExists path\n  if exists then do',
         '  present <- fileExists path\n  if present then do'),
        ('superviseBudget budget config helper cwd directory options total entries index = case entries of\n',
         'superviseBudget : B.Budget -> Config -> String -> String -> String -> R.Options -> Int -> List C.Case -> Int -> IO (List J.Json)\nsuperviseBudget budget config helper cwd directory options total entries index = case entries of\n'),
    ],
}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def repair_bytes(path, original):
    if path not in EDITS:
        raise ValueError('unreviewed framework repair: ' + path)
    value = original.decode('utf-8')
    for before, after in EDITS[path]:
        if value.count(before) != 1:
            raise ValueError('ambiguous frozen framework input: ' + path)
        value = value.replace(before, after, 1)
    return value.encode('utf-8')


def verify_repairs(root, revision=None):
    sources = {}
    for path in EDITS:
        original = subprocess.check_output(
            ['git', '--no-replace-objects', 'show', FROZEN_FRAMEWORK + ':' + path], cwd=root)
        expected = repair_bytes(path, original)
        actual = ((root / path).read_bytes() if revision is None else subprocess.check_output(
            ['git', '--no-replace-objects', 'show', revision + ':' + path], cwd=root))
        if actual != expected:
            raise ValueError('framework source exceeds reviewed repair: ' + path)
        sources[path] = (digest(original), digest(expected))
    return sources


def strict_object(pairs):
    value = {}
    for key, entry in pairs:
        if key in value:
            raise ValueError('duplicate lock key: ' + key)
        value[key] = entry
    return value


def repaired_root_lock(root, original, revision=None):
    """Change only hashes of the three repaired modules in the frozen root graph."""
    repairs = verify_repairs(root, revision)
    value = json.loads(original, object_pairs_hook=strict_object)
    expected_paths = {path for path in EDITS if path.startswith('testing/Test/')}
    seen = set()
    for package in value['packages']:
        for relative, prior_hash in package['sources'].items():
            path = package['path'] + '/' + relative
            if path in expected_paths:
                if path in seen or prior_hash != repairs[path][0]:
                    raise ValueError('frozen lock repair source differs: ' + path)
                seen.add(path)
                package['sources'][relative] = repairs[path][1]
    if seen != expected_paths:
        raise ValueError('frozen root lock lacks the exact repaired module set')
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode('utf-8')
