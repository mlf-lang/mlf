"""Independent transport/contracts for the explicitly different split strategy."""
from pathlib import Path
import re
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HELPER = ROOT / 'tools/performance/a1-private-index/helper.py'
H = types.ModuleType('split_guard')
H.__file__ = str(HELPER)
exec(compile(HELPER.read_bytes(), str(HELPER), 'exec'), H.__dict__)
LIMITS = dict(address_space_per_process_bytes=6*1024**3,
              disk_free_floor_bytes=5*1024**3, host_available_floor_bytes=3*1024**3,
              max_work_bytes=4*1024**3, process_tree_rss_bytes=5*1024**3,
              wall_seconds=600)
COUNTS = {'mlf-foundation': 14, 'mlf-language-core': 4, 'mlf-frontend': 11,
          'mlf-xmlf': 6, 'mlf-inference': 11, 'mlf-interpreter': 2,
          'mlf-llvm': 13, 'mlf-crates': 21, 'mlf-package-core': 2, 'entry': 6}
BASE = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'


def pack(values):
    return ''.join(str(len(value))+':'+value for value in values)


def imports(path):
    return re.findall(r'(?m)^\s*import\s+(?:qualified\s+)?([A-Z][\w.]*)',
                      Path(path).read_text())


def row(name, path, relative):
    return dict(module=name, source=str(path), relative=relative,
                bytes=path.stat().st_size, sha256=H.sha(path))


def topological(slices):
    by_name = {item['name']: item for item in slices}
    H.require(len(by_name) == len(slices), 'duplicate slice')
    active, done, ordered = set(), set(), []
    def visit(name):
        H.require(name in by_name, 'unknown slice dependency '+name)
        H.require(name not in active, 'slice cycle '+name)
        if name in done:
            return
        active.add(name)
        for dependency in sorted(by_name[name]['dependencies']):
            visit(dependency)
        active.remove(name)
        done.add(name)
        ordered.append(by_name[name])
    for name in sorted(by_name):
        visit(name)
    return ordered


def validate(plan):
    H.require(plan['format'] == 'fresh-split-v1', 'unknown split plan')
    slices = plan['slices']
    rows = [item for part in slices for item in part['modules']]
    H.require(len({r['module'] for r in rows}) == len(rows), 'nonunique module ownership')
    H.require(len({r['source'] for r in rows}) == len(rows), 'duplicate source path')
    H.require(plan['module_count'] == len(rows), 'module count differs')
    H.require(plan['source_bytes'] == sum(r['bytes'] for r in rows), 'source bytes differ')
    ordered = topological(slices)
    H.require(slices == ordered, 'slices not in frozen topological order')
    owner = {r['module']: part['name'] for part in slices for r in part['modules']}
    for part in slices:
        H.require(part['modules'], 'empty slice')
        H.require(len(set(part['dependencies'])) == len(part['dependencies']), 'duplicate dependency')
        for item in part['modules']:
            path = H.regular(item['source'])
            H.require(path.stat().st_size == item['bytes'] and H.sha(path) == item['sha256'],
                      'source bytes changed '+item['module'])
            for name in imports(path):
                if name == 'MLF.Primitive':
                    continue
                H.require(name in owner, 'unlisted imported module '+name)
                H.require(owner[name] == part['name'] or owner[name] in part['dependencies'],
                          'missing direct slice dependency '+item['module']+' -> '+name)
    H.require(sum(bool(s['entry']) for s in slices) == 1 and slices[-1]['entry'],
              'one final entry slice required')
    if plan['kind'] == 'compiler90':
        H.require({s['name']: len(s['modules']) for s in slices} == COUNTS,
                  'exact nine libraries plus entry ownership')
        H.require(len(rows) == 90 and plan['source_bytes'] == 5233364, 'exact B0 input size')
        H.require(slices[-1]['entry'] == 'MLF.Entry.Emlf', 'same compiler entry')
        H.require(plan['baseline_commit'] == BASE, 'baseline label differs')
        workload = H.load(plan['workload'])
        H.require(workload['baseline_ref'] == BASE
                  and workload['format'] == 'full-emlf-source-closure-v1'
                  and workload['entry'] == 'MLF.Entry.Emlf'
                  and workload['module_count'] == 90 and workload['source_bytes'] == 5233364
                  and workload['nonshared_imports'] == ['MLF.Primitive'], 'B0 workload identity differs')
        H.require(H.sha(plan['workload']) == plan['workload_sha256'], 'B0 workload changed')
        expected = {r['module']: r for r in workload['modules']}
        H.require(len(expected) == len(workload['modules']) == 90
                  and expected == {r['module']: r for r in rows}, 'B0 frozen rows differ')
        H.require(workload['input_files'] == {r['source']: r['sha256'] for r in rows},
                  'B0 frozen source pins differ')
        source = Path(plan['source'])
        required_static = [Path(plan['workload']), source/'shared-sources.json', source/'mlf-package.json']
        for part in slices:
            if part['name'] == 'entry':
                target = H.load(source/'mlf-package.json')['executables']['emlf']
                owned = dict(target['modules'])
                owned['MLF.Entry.Emlf'] = target['main']
                actual = {name: str((source/path).resolve()) for name,path in owned.items()}
                dependencies = target['dependencies']
            else:
                manifest_path = source/'libraries'/part['name']/'mlf-package.json'
                required_static.append(manifest_path)
                manifest = H.load(manifest_path)
                actual = {name: str((manifest_path.parent/path).resolve())
                          for name,path in manifest['library']['modules'].items() if name in expected}
                dependencies = list(manifest.get('dependencies', {}))
            H.require(actual == {r['module']:r['source'] for r in part['modules']},
                      'slice differs from original package ownership')
            H.require(sorted(dependencies) == part['dependencies'], 'original direct dependencies differ')
        H.require(set(plan['static_pins']) == {str(path) for path in required_static},
                  'incomplete manifest/workload pins')
        H.check_pins(plan['static_pins'])
        # A second closure walk ignores the plan topology and package ownership.
        source = Path(plan['source'])
        manifest = H.load(source/'shared-sources.json')
        known = {r['module']: r for r in manifest['modules']}
        H.require(len(known) == len(manifest['modules']), 'duplicate shared manifest module')
        seen, outside = set(), set()
        def visit(name):
            if name in seen:
                return
            if name not in known:
                outside.add(name)
                return
            seen.add(name)
            for dep in imports(source/known[name]['path']):
                visit(dep)
        visit('MLF.Entry.Emlf')
        H.require(seen == set(owner) and outside == {'MLF.Primitive'}, 'independent B0 closure differs')
        for item in rows:
            H.require(Path(item['source']) == (source/known[item['module']]['path']).resolve(),
                      'source path differs from shared manifest')
    else:
        H.require(plan['kind'] == 'fixture', 'unknown experiment kind')
    return {r['source']: r['sha256'] for r in rows}


def fresh(report, identity):
    H.require(report['crate'] == identity, 'wrong query crate')
    groups = report['groups']
    H.require(report['reused_groups'] == 0 and report['inferred_groups'] == len(groups) > 0,
              'all target groups must infer freshly')
    H.require(all(g['cached'] is False for g in groups), 'target cache hit')
    H.require(len({g['id'] for g in groups}) == len(groups), 'duplicate query identity')
    return len(groups)


def interface(text, identity, modules, dependencies):
    lines = text.splitlines()
    H.require(lines and lines[0] == 'crate '+identity, 'wrong interface identity')
    actual = [line[7:] for line in lines if line.startswith('module ')]
    H.require(len(actual) == len(modules) and set(actual) == set(modules),
              'interface module ownership differs')
    # Parse from the ends, allowing spaces in a dependency's absolute path.
    deps = [line[11:].split(' ', 1) for line in lines if line.startswith('dependency ')]
    found = [(name, tail.rsplit(' ', 1)[0]) for name, tail in deps]
    H.require(len(found) == len(dependencies) and dict(found) == dependencies,
              'interface direct dependency identities/paths differ')
