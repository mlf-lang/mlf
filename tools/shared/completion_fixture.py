import json
from pathlib import Path

# Synthetic filesystem artifacts, never native compilation/qualification.
# Adapted from existing StageControls; b is injected by the test module.

class StageFixture:
    def __init__(self, root, output, name, producer):
        self.root = root
        self.stage = output / ('stage-' + name)
        self.cache = output / ('cache-' + name)
        self.pair = producer / 'bin' if name == 'A' else output / 'stage-A/bin'
        self.output = output
        self.name = name
        self.helper = self.file('helper', b'helper') if name == 'A' else output / 'stage-A/bin/mlf-build-runner'
        self.clang = self.file('clang', b'clang')
        if name == 'A':
            self.file('pair/emlf', b'compiler')
            self.file('pair/mlfpkg', b'manager')
        self.runtime = {str(self.file('runtime/mlf_runtime.c', b'runtime')): b.sha(self.root / 'runtime/mlf_runtime.c')}
        self.runtime[str(self.root / 'runtime/mlf_build_runner.c')] = b.sha(self.root / 'runtime/mlf_build_runner.c')
        self.targets = {t: {'main': t+'.hs'} for t in b.TARGETS}
        self.manifest = {'format': 1, 'name': 'mlf-compiler', 'version': '0.3.0', 'executables': self.targets}
        manifest = self.file('mlf-package.json', json.dumps(self.manifest).encode())
        sources = {}; self.source_values = {}; self.crates = []
        for target in b.TARGETS:
            name = 'Entry.' + target.capitalize()
            source = self.file(target+'.hs', ('-- mlf:syntax shared-haskell-v1\nmodule '+name+' where {}\n').encode())
            sources[source.name] = b.sha(source)
            self.source_values[target] = {name: {'path': str(source), 'sha256': b.sha(source), 'syntax': 'shared-haskell-v1'}}
            self.crates.append({'crate': 'mlf-compiler/0.3.0/target-'+target, 'entry': name, 'modules': [name], 'dependencies': []})
        self.packages = [{'name': 'mlf-compiler', 'version': '0.3.0', 'path': '.', 'manifest': b.sha(manifest), 'sources': sources}]
        self.rows = []
        self.artifacts = {}
        self.jobs = [{'id': 'runtime', 'kind': 'runtime', 'dependencies': []}]
        self.log = self.file('stage/commands/0.log', b'ok')
        self.plan = self.file('stage/invocations/plan.bin', b'plan')
        self.base_tools = {'clang': self.identity(self.clang), 'system': 'Linux', 'machine': 'x86_64',
                           'native_environment': {}, 'gmp': {'flags': ['-lgmp'], 'libraries': {}, 'headers': {}},
                           'runtime': self.runtime, 'runtime-path': str(self.root/'runtime/mlf_runtime.c')}
        self.gc = {'flags': ['-lgc'], 'libraries': {}, 'headers': {}}
        self.runtime_hash = self.digest(b'runtime object')
        self.artifact(20, 'runtime object', {**self.base_tools, 'gc': self.gc, 'flags': ['-O2','-std=c11']}, {'runtime.o': b'runtime object'})
        for n, target in enumerate(b.TARGETS):
            llvm, obj, native = (target.encode() + suffix for suffix in (b' llvm', b' object', b' native'))
            llvm_hash, obj_hash, native_hash = [self.digest(v) for v in (llvm, obj, native)]
            crate_path = self.cache / f'{30+n*10:064x}'
            self.artifact(30+n*10, 'crate mlf-compiler/0.3.0/target-' + target,
                          {'compiler': self.identity(self.pair/'emlf'), 'manager': self.identity(self.pair/'mlfpkg'),
                           'crate': 'mlf-compiler/0.3.0/target-'+target, 'entry': 'Entry.'+target.capitalize(),
                           'no-prelude': False, 'sources': self.source_values[target], 'dependencies': []},
                          {'unit.mlfci': b'meta', 'unit.mlfco': b'xmlf'})
            self.artifact(31+n*10, 'LLVM emission', {'compiler': self.identity(self.pair/'emlf'),
                          'crate-path': str(crate_path), 'metadata': self.digest(b'meta'), 'object': self.digest(b'xmlf')}, {'program.ll': llvm})
            self.artifact(1+n*3, 'LLVM object', {**self.base_tools, 'llvm': llvm_hash, 'flags': ['-O2','-Wno-override-module','-c']}, {'program.o': obj})
            self.artifact(2+n*3, 'native link', {**self.base_tools, 'gc': self.gc, 'llvm-object': obj_hash, 'runtime-object': self.runtime_hash, 'flags': ['-O2','-Wno-override-module','-lgmp','-lgc','-lm']}, {'program': native})
            self.artifact(3+n*3, 'executable mlf-compiler:' + target,
                          {'target': self.targets[target], 'crate-path': str(crate_path), 'llvm': llvm_hash, 'binary': native_hash,
                           'metadata': self.digest(b'meta'), 'object': self.digest(b'xmlf')},
                          {'program.ll': llvm, 'program': native, 'unit.mlfci': b'meta', 'unit.mlfco': b'xmlf'})
            self.file('stage/bin/' + target, native)
            self.jobs.extend([
                {'id': 'crate-'+target, 'kind': 'target', 'dependencies': [], 'entry': 'Entry.'+target.capitalize(),
                 'modules': [{'name': n, 'source': v['path']} for n,v in self.source_values[target].items()]},
                {'id': 'emit-'+target, 'kind': 'emit', 'crate': 'crate-'+target, 'dependencies': ['crate-'+target]},
                {'id': 'object-'+target, 'kind': 'object', 'emitted': 'emit-'+target, 'dependencies': ['emit-'+target]},
                {'id': 'link-'+target, 'kind': 'link', 'llvm': 'object-'+target, 'runtime': 'runtime', 'dependencies': ['object-'+target,'runtime']},
                {'id': 'assemble-'+target, 'kind': 'assemble', 'crate': 'crate-'+target, 'emitted': 'emit-'+target,
                 'linked': 'link-'+target, 'dependencies': ['crate-'+target,'emit-'+target,'link-'+target], 'selection': {'name': target, 'target': self.targets[target]}}])
        self.file('stage/bin/mlf-build-runner', b'helper')
        self.report = {'complete': True, 'implementation': 'MLF',
                       'toolchain': {**self.base_tools, 'compiler': self.identity(self.pair/'emlf'),
                                     'manager': self.identity(self.pair/'mlfpkg'), 'pkg-config': self.identity(self.clang),
                                     'clang': self.identity(self.clang), 'runtime': self.runtime},
                       'scheduler': [{'helper': self.identity(self.helper), 'plan': str(self.plan),
                                      'plan_digest': b.sha(self.plan)}],
                       'commands': [{'exit_code': 0, 'stdout': str(self.log), 'stderr': str(self.log)}],
                       'builds': self.rows}
        self.report['packages'] = {'format': 1, 'packages': self.packages}
        context = self.file('stage/invocations/context.json', json.dumps({'jobs': self.jobs,
            'tools': self.report['toolchain'], 'initial': self.report['packages'],
            'config': {'cache-dir': str(self.cache), 'build-directory': str(self.stage), 'jobs': '1'},
            'graph': {'packages': [{'path': str(self.root/'mlf-package.json'), 'data': self.manifest, 'modules': []}]}}).encode())
        invocation = b.sha(context)
        outcome = {'protocol_version': 1, 'complete': True, 'invocation_id': invocation,
                   'plan_digest': b.sha(self.plan), 'jobs': 1, 'exit_code': 0,
                   'tasks': [{'id': j['id'], 'state': 'succeeded', 'exit_code': 0} for j in self.jobs]}
        self.file('stage/invocations/runner-result.json', json.dumps(outcome).encode())
        self.report['scheduler'][0].update(invocation_id=invocation, jobs=self.jobs)
        self.report['scheduler_results'] = [outcome]
        for job, row in zip(self.jobs, self.rows):
            directory = self.cache/row['key']; value = b.read(directory/'artifact.json')
            worker_report = {'builds': [row.copy()]}
            self.file('stage/invocations/jobs/'+job['id']+'/build-report.json', json.dumps(worker_report).encode())
            self.file('stage/invocations/jobs/'+job['id']+'/result.json', json.dumps(
                {'complete': True, 'id': job['id'], 'invocation_id': invocation, 'report': worker_report,
                 'result': {**row, 'artifact': str(directory), 'files': value['files']}}).encode())
            row['job_id'] = job['id']
        self.report['native_inputs'] = [self.gc]
        self.report['cache_directory'] = str(self.cache)
        for target in b.TARGETS:
            directory = self.artifacts['executable mlf-compiler:'+target]
            value = b.read(directory/'artifact.json')
            value['inputs']['toolchain'] = self.report['toolchain']
            (directory/'artifact.json').write_text(json.dumps(value))
        self.save()

    def file(self, name, content):
        if name == 'helper':
            p = self.output / 'tools/mlf-build-runner'
        elif name.startswith('stage/'):
            p = self.stage / name[6:]
        elif name.startswith('cache/'):
            p = self.cache / name[6:]
        elif name.startswith('pair/'):
            p = self.pair / name[5:]
        else:
            p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def identity(self, path):
        return {'path': str(path), 'sha256': b.sha(path)}

    def digest(self, value):
        import hashlib
        return hashlib.sha256(value).hexdigest()

    def artifact(self, number, kind, inputs, files):
        key = f'{number:064x}'
        row = {'key': key, 'kind': kind, 'cached': False}
        self.rows.append(row)
        hashes = {}
        for name, data in files.items():
            p = self.file('cache/' + key + '/' + name, data)
            hashes[name] = b.sha(p)
        self.file('cache/' + key + '/artifact.json', json.dumps(
            {'key': key, 'inputs': inputs, 'files': hashes}).encode())
        self.artifacts[kind] = self.cache / key

    def save(self):
        self.file('stage/build-report.json', json.dumps(self.report).encode())

    def verify(self):
        return b.verify_stage(self.stage, self.cache, self.pair, self.helper, self.clang, self.runtime, self.packages, self.targets, self.clang, self.crates, self.root)

